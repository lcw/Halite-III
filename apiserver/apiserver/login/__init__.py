import flask
import sqlalchemy
from flask_oauthlib.client import OAuth

from .. import app, config, model, util


oauth_login = flask.Blueprint("github_login", __name__)
oauth = OAuth(app)
github = oauth.remote_app(
    "github",
    consumer_key=config.OAUTH_GITHUB_CONSUMER_KEY,
    consumer_secret=config.OAUTH_GITHUB_CONSUMER_SECRET,
    request_token_params={"scope": "user:email"},
    base_url="https://api.github.com",
    request_token_url=None,
    access_token_method="POST",
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
)


@oauth_login.route("/github")
def github_login_init():
    return github.authorize(
        callback=flask.url_for(".github_login_callback", _external=True))


@oauth_login.route("/response/github")
def github_login_callback():
    response = github.authorized_response()
    if response is None or response.get("access_token") is None:
        raise util.APIError(
            401,
            message="Access denied. Reason: {}. Error: {}.".format(
                flask.request.args["error"],
                flask.request.args["error_description"],
            )
        )

    flask.session["github_token"] = (response["access_token"], "")

    user_data = github.get("user").data

    username = user_data["login"]
    github_user_id = user_data["id"]
    emails = github.get("user/emails").data

    email = emails[0]["email"]
    for record in emails:
        if record["primary"]:
            email = record["email"]
            break

    with model.engine.connect() as conn:
        user = conn.execute(sqlalchemy.sql.select([
            model.users.c.userID,
        ]).select_from(model.users).where(
            (model.users.c.oauthProvider == 1) &
            (model.users.c.oauthID == github_user_id)
        )).first()

        if not user:
            # New user
            rank = conn.execute(sqlalchemy.sql.select([
                sqlalchemy.sql.func.count()
            ]).select_from(model.users)).first()[0]
            new_user_id = conn.execute(model.users.insert().values(
                username=username,
                githubEmail=email,
                oauthID=github_user_id,
                oauthProvider=1,
                rank=rank,
            )).inserted_primary_key
            flask.session["user_id"] = new_user_id
        else:
            flask.session["user_id"] = user["userID"]

    if flask.request.params.get("redirectURL"):
        return flask.redirect(flask.request.params["redirectURL"])
    return flask.redirect("/")


@github.tokengetter
def github_tokengetter():
    return flask.session.get("github_token")
