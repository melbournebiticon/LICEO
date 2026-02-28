from flask import Flask
from routes import init_routes

app = Flask(__name__)
app.secret_key = "liceo_secret_key"

# initialize all routes (register blueprints + uploads route)
init_routes(app)

if __name__ == "__main__":
    app.run(debug=True)

