from flask import Flask
from src import database
from src.models import *

app = Flask(__name__)

# Configurações do banco de dados MySQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:@localhost/drh_sistema'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializa a extensão de banco de dados
database.init_app(app)

# Cria as tabelas no banco de dados MySQL
with app.app_context():
    database.create_all()
