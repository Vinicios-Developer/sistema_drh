import os
import pytz
import pandas as pd
from flask import render_template, redirect, url_for, request, flash, jsonify, session, send_file
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from src import app, database, bcrypt
from src.forms import FormLogin, FormMilitar, FormCriarUsuario
from src.models import (Militar, PostoGrad, Quadro, Obm, Localidade, Funcao, Situacao, User, FuncaoUser, PublicacaoBg,
                        EstadoCivil, Especialidade, Destino, Agregacoes, Punicao, Comportamento, MilitarObmFuncao,
                        FuncaoGratificada,
                        MilitaresAgregados, MilitaresADisposicao, LicencaEspecial, LicencaParaTratamentoDeSaude)
from src.querys import obter_estatisticas_militares
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderServiceError
from src.controller.control import checar_ocupacao
from src.controller.business_logic import processar_militares_a_disposicao, processar_militares_agregados, \
    processar_militares_le, processar_militares_lts
from datetime import datetime
from io import BytesIO
from sqlalchemy.orm import aliased


@app.route("/")
@login_required
def home():
    try:
        # enviando e-mails
        processar_militares_agregados()
        processar_militares_a_disposicao()
        processar_militares_le()
        processar_militares_lts()

        militares_le = LicencaEspecial.query.all()

        militares_lts = LicencaParaTratamentoDeSaude.query.all()

        # estatísticas dos militares para o dashboard
        estatisticas = obter_estatisticas_militares()

        return render_template('home.html', **estatisticas, militares_le=militares_le, militares_lts=militares_lts)
    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'error': 'Erro ao carregar a página'}), 500


def get_user_ip():
    # Verifica se o cabeçalho X-Forwarded-For está presente
    if request.headers.get('X-Forwarded-For'):
        # Pode conter múltiplos IPs, estou pegando o primeiro
        ip = request.headers.getlist('X-Forwarded-For')[0]
    else:
        # Fallback para o IP remoto
        ip = request.remote_addr
    return ip


@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        flash('Você já está logado.', 'alert-info')
        return redirect(url_for('home'))

    form_login = FormLogin()
    if form_login.validate_on_submit() and 'botao_submit_login' in request.form:
        cpf = User.query.filter_by(cpf=form_login.cpf.data).first()

        if cpf and bcrypt.check_password_hash(cpf.senha, form_login.senha.data):
            login_user(cpf, remember=form_login.lembrar_dados.data)
            flash('Login feito com sucesso!', 'alert-success')

            fuso_horario = pytz.timezone('America/Manaus')
            cpf.data_ultimo_acesso = datetime.now(fuso_horario)
            cpf.ip_address = get_user_ip()

            # Capturar latitude e longitude do formulário
           # latitude = request.form.get('latitude')
           # longitude = request.form.get('longitude')

            # Atualizar os campos de latitude e longitude no banco de dados
         #  cpf.latitude = latitude
           # cpf.longitude = longitude

            # Usar geopy com Nominatim para obter o endereço
          #if latitude and longitude:
               # try:
                    #geolocator = Nominatim(user_agent="MeuApp")
                   # location = geolocator.reverse((latitude, longitude), exactly_one=True, zoom=18)
                  #  if location and location.address:
                   #     cpf.endereco_acesso = location.address
                   # else:
                   #     cpf.endereco_acesso = 'Endereço não encontrado'
               # except GeocoderServiceError as e:
                  #  print(f"Erro na geocodificação reversa: {e}")
                  #  cpf.endereco_acesso = 'Erro na API de geocodificação'

            database.session.commit()

            return redirect(url_for('home'))
        else:
            flash('Falha no Login, e-mail ou senha incorretos.', 'alert-danger')

    return render_template('login.html', form_login=form_login)


@app.route("/criar-conta", methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE')
def criar_conta():
    form_criar_usuario = FormCriarUsuario()

    choices = [(funcao_user.id, funcao_user.ocupacao) for funcao_user in FuncaoUser.query.all()]
    choices.insert(0, ('', '-- Selecione uma opção --'))
    form_criar_usuario.funcao_user_id.choices = choices

    if form_criar_usuario.validate_on_submit():
        senha_cript = bcrypt.generate_password_hash(form_criar_usuario.senha.data)
        usuarios = User(nome=form_criar_usuario.nome.data,
                        email=form_criar_usuario.email.data,
                        funcao_user_id=form_criar_usuario.funcao_user_id.data,
                        cpf=form_criar_usuario.cpf.data,
                        senha=senha_cript)
        database.session.add(usuarios)
        database.session.commit()
        flash("Usuário cadastrado com sucesso!", "alert-success")
        return redirect(url_for('home'))
    return render_template('criar_conta.html', form_criar_usuario=form_criar_usuario)


@app.route("/adicionar-militar", methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA')
def adicionar_militar():
    form_militar = FormMilitar()

    form_militar.funcao_gratificada_id.choices = [
                                                  ('', '-- Selecione uma opção --')
                                              ] + [(funcao_gratificada.id, funcao_gratificada.gratificacao) for
                                                   funcao_gratificada in FuncaoGratificada.query.all()]

    form_militar.posto_grad_id.choices = [
                                             ('', '-- Selecione uma opção --')
                                         ] + [(posto.id, posto.sigla) for posto in PostoGrad.query.all()]

    form_militar.quadro_id.choices = [
                                         ('', '-- Selecione uma opção --')
                                     ] + [(quadro.id, quadro.quadro) for quadro in Quadro.query.all()]

    form_militar.localidade_id.choices = [
                                             ('', '-- Selecione uma opção --')
                                         ] + [(localidade.id, localidade.sigla) for localidade in
                                              Localidade.query.all()]

    form_militar.obm_ids_1.choices = [
                                         ('', '-- Selecione uma opção --')] + [(obm.id, obm.sigla) for obm in
                                                                               Obm.query.all()]

    form_militar.funcao_ids_1.choices = [
                                            ('', '-- Selecione uma opção --')] + [(funcao.id, funcao.ocupacao) for
                                                                                  funcao in Funcao.query.all()]

    form_militar.obm_ids_2.choices = [
                                         ('', '-- Selecione uma opção --')] + [(obm.id, obm.sigla) for obm in
                                                                               Obm.query.all()]

    form_militar.funcao_ids_2.choices = [
                                            ('', '-- Selecione uma opção --')] + [(funcao.id, funcao.ocupacao) for
                                                                                  funcao in Funcao.query.all()]

    form_militar.situacao_id.choices = [
                                           ('', '-- Selecione uma opção --')
                                       ] + [(situacao.id, situacao.condicao) for situacao in Situacao.query.all()]

    form_militar.estado_civil.choices = [
                                            ('', '-- Selecione uma opção --')
                                        ] + [(estado.id, estado.estado) for estado in EstadoCivil.query.all()]

    form_militar.especialidade_id.choices = [
                                                ('', '-- Selecione uma opção --')
                                            ] + [(especialidade.id, especialidade.ocupacao) for especialidade in
                                                 Especialidade.query.all()]

    form_militar.destino_id.choices = [
                                          ('', '-- Selecione uma opção --')
                                      ] + [(destino.id, destino.local) for destino in Destino.query.all()]

    form_militar.agregacoes_id.choices = [
                                             ('', '-- Selecione uma opção --')
                                         ] + [(agregacoes.id, agregacoes.tipo) for agregacoes in Agregacoes.query.all()]

    form_militar.punicao_id.choices = [
                                       ('', '-- Selecione uma opção --')
                                   ] + [(punicao.id, punicao.sancao) for punicao in Punicao.query.all()]

    form_militar.comportamento_id.choices = [
                                             ('', '-- Selecione uma opção --')
                                         ] + [(comportamento.id, comportamento.conduta) for comportamento in
                                              Comportamento.query.all()]

    if form_militar.validate_on_submit():

        completa_25_inclusao = datetime.strptime(form_militar.completa_25_inclusao.data, '%d/%m/%Y').date()
        completa_30_inclusao = datetime.strptime(form_militar.completa_30_inclusao.data, '%d/%m/%Y').date()
        completa_25_anos_sv = datetime.strptime(form_militar.completa_25_anos_sv.data, '%d/%m/%Y').date()
        completa_30_anos_sv = datetime.strptime(form_militar.completa_30_anos_sv.data, '%d/%m/%Y').date()

        militar = Militar(
            nome_completo=form_militar.nome_completo.data,
            nome_guerra=form_militar.nome_guerra.data,
            cpf=form_militar.cpf.data,
            rg=form_militar.rg.data,
            nome_pai=form_militar.nome_pai.data,
            nome_mae=form_militar.nome_mae.data,
            matricula=form_militar.matricula.data,
            pis_pasep=form_militar.pis_pasep.data,
            num_titulo_eleitor=form_militar.num_titulo_eleitor.data,
            digito_titulo_eleitor=form_militar.digito_titulo_eleitor.data,
            zona=form_militar.zona.data,
            secao=form_militar.secao.data,
            posto_grad_id=form_militar.posto_grad_id.data,
            quadro_id=form_militar.quadro_id.data,
            localidade_id=form_militar.localidade_id.data,
            antiguidade=form_militar.antiguidade.data,
            sexo=form_militar.sexo.data,
            raca=form_militar.raca.data,
            data_nascimento=form_militar.data_nascimento.data,
            inclusao=form_militar.inclusao.data,
            completa_25_inclusao=completa_25_inclusao,
            completa_30_inclusao=completa_30_inclusao,
            punicao_id=form_militar.punicao_id.data,
            comportamento_id=form_militar.comportamento_id.data,
            efetivo_servico=form_militar.efetivo_servico.data,
            completa_25_anos_sv=completa_25_anos_sv,
            completa_30_anos_sv=completa_30_anos_sv,
            anos=form_militar.anos.data,
            meses=form_militar.meses.data,
            dias=form_militar.dias.data,
            total_dias=form_militar.total_dias.data,
            idade_reserva_grad=form_militar.idade_reserva_grad.data,
            estado_civil=form_militar.estado_civil.data,
            especialidade_id=form_militar.especialidade_id.data,
            pronto=form_militar.pronto.data,
            situacao_id=form_militar.situacao_id.data,
            agregacoes_id=form_militar.agregacoes_id.data,
            destino_id=form_militar.destino_id.data,
            inicio_periodo=form_militar.inicio_periodo.data,
            fim_periodo=form_militar.fim_periodo.data,
            ltip_afastamento_cargo_eletivo=form_militar.ltip_afastamento_cargo_eletivo.data,
            periodo_ltip=form_militar.periodo_ltip.data,
            total_ltip=form_militar.total_ltip.data,
            completa_25_anos_ltip=form_militar.completa_25_anos_ltip.data,
            completa_30_anos_ltip=form_militar.completa_30_anos_ltip.data,
            cursos=form_militar.cursos.data,
            grau_instrucao=form_militar.grau_instrucao.data,
            graduacao=form_militar.graduacao.data,
            pos_graduacao=form_militar.pos_graduacao.data,
            mestrado=form_militar.mestrado.data,
            doutorado=form_militar.doutorado.data,
            cfsd=form_militar.cfsd.data,
            cfc=form_militar.cfc.data,
            cfs=form_militar.cfs.data,
            cas=form_militar.cas.data,
            choa=form_militar.choa.data,
            cfo=form_militar.cfo.data,
            cbo=form_militar.cbo.data,
            cao=form_militar.cao.data,
            csbm=form_militar.csbm.data,
            cursos_civis=form_militar.cursos_civis.data,
            endereco=form_militar.endereco.data,
            complemento=form_militar.complemento.data,
            cidade=form_militar.cidade.data,
            estado=form_militar.estado.data,
            cep=form_militar.cep.data,
            celular=form_militar.celular.data,
            email=form_militar.email.data,
            inclusao_bg=form_militar.inclusao_bg.data,
            soldado_tres=form_militar.soldado_tres.data,
            soldado_dois=form_militar.soldado_dois.data,
            soldado_um=form_militar.soldado_um.data,
            cabo=form_militar.cabo.data,
            terceiro_sgt=form_militar.terceiro_sgt.data,
            segundo_sgt=form_militar.segundo_sgt.data,
            primeiro_sgt=form_militar.primeiro_sgt.data,
            subtenente=form_militar.subtenente.data,
            segundo_tenente=form_militar.segundo_tenente.data,
            primeiro_tenente=form_militar.primeiro_tenente.data,
            cap=form_militar.cap.data,
            maj=form_militar.maj.data,
            tc=form_militar.tc.data,
            cel=form_militar.cel.data,
            funcao_gratificada_id=form_militar.funcao_gratificada_id.data,
            alteracao_nome_guerra=form_militar.alteracao_nome_guerra.data,
            ip_address=get_user_ip(),
            usuario_id=current_user.id
        )
        arquivos = form_militar.arquivo.data

        # Se for um único arquivo, transforme-o em uma lista para uniformizar o processamento
        if not isinstance(arquivos, list):
            arquivos = [arquivos]

        for arquivo in arquivos:
            if isinstance(arquivo, str):
                # Esse erro não deve acontecer se o upload foi feito corretamente, mas informe o usuário se ocorrer
                print(f"Erro: Esperado um objeto FileStorage, mas obtido uma string: {arquivo}")
            elif arquivo:  # Verifica se o arquivo não está vazio
                nome_seguro = secure_filename(arquivo.filename)
                caminho = os.path.join(os.path.abspath(os.path.dirname(__file__)), app.config["UPLOAD_FOLDER"],
                                       nome_seguro)
                arquivo.save(caminho)  # Salva o arquivo no caminho especificado
                print(f"Arquivo {nome_seguro} salvo com sucesso em {caminho}")
            else:
                print("Erro: O arquivo está vazio ou é inválido.")

        database.session.add(militar)
        database.session.commit()

        # Adicionando as OBMs e Funções
        obm_funcao_pairs = zip(request.form.getlist('obm_ids_1'), request.form.getlist('funcao_ids_1'))

        # Itera sobre as combinações selecionadas de OBMs e funções
        for obm_id, funcao_id in obm_funcao_pairs:
            # Verifica se obm_id e funcao_id não estão vazios
            if obm_id and funcao_id:
                militar_obm_funcao = MilitarObmFuncao(
                    militar_id=militar.id,
                    obm_id=int(obm_id),  # Certifique-se de que o ID é um número inteiro
                    tipo=1,
                    funcao_id=int(funcao_id)  # Certifique-se de que o ID é um número inteiro
                )
                database.session.add(militar_obm_funcao)

        # Repetindo o processo para o segundo conjunto de OBMs e funções (caso exista)
        obm_funcao_pairs_2 = zip(request.form.getlist('obm_ids_2'), request.form.getlist('funcao_ids_2'))

        for obm_id_2, funcao_id_2 in obm_funcao_pairs_2:
            if obm_id_2 and funcao_id_2:
                militar_obm_funcao = MilitarObmFuncao(
                    militar_id=militar.id,
                    obm_id=int(obm_id_2),  # Certifique-se de que o ID é um número inteiro
                    tipo=2,
                    funcao_id=int(funcao_id_2)  # Certifique-se de que o ID é um número inteiro
                )
                database.session.add(militar_obm_funcao)

        database.session.commit()

        # Salvando as publicações de BG
        campos_bg = [
            'transferencia', 'situacao_militar', 'cfsd', 'cfc', 'cfs', 'cas',
            'choa', 'cfo', 'cbo', 'cao', 'csbm', 'soldado_tres',
            'soldado_dois', 'soldado_um', 'cabo', 'terceiro_sgt',
            'segundo_sgt', 'primeiro_sgt', 'subtenente',
            'publicidade_segundo_tenente', 'publicidade_primeiro_tenente',
            'pub_cap', 'pub_maj', 'pub_tc', 'pub_cel', 'pub_alteracao'
        ]

        for campo in campos_bg:
            boletim_geral = getattr(form_militar, campo).data
            if boletim_geral:
                publicacao_bg = PublicacaoBg(
                    militar_id=militar.id,
                    boletim_geral=boletim_geral,
                    tipo_bg=campo
                )
                database.session.add(publicacao_bg)

        # Verifica se a situação selecionada é "AGREGADO"
        situacao_selecionada = Situacao.query.get(form_militar.situacao_id.data)
        if situacao_selecionada and situacao_selecionada.condicao == 'AGREGADO':

            # Verifica se há uma publicação BG associada ao militar e à situação
            publicacao_situacao_bg = PublicacaoBg.query.filter_by(militar_id=militar.id,
                                                                  tipo_bg='situacao_militar').first()

            if publicacao_situacao_bg:
                # Criando o registro em 'militares_agregados'
                militar_agregado = MilitaresAgregados(
                    militar_id=militar.id,
                    posto_grad_id=form_militar.posto_grad_id.data,
                    quadro_id=form_militar.quadro_id.data,
                    destino_id=form_militar.destino_id.data,
                    situacao_id=situacao_selecionada.id,
                    inicio_periodo=form_militar.inicio_periodo.data,
                    fim_periodo_agregacao=form_militar.fim_periodo.data,
                    publicacao_bg_id=publicacao_situacao_bg.id
                )

                # Atualizando a posição da agregação (vigente ou término)
                militar_agregado.atualizar_status()

                # Adiciona o registro de agregação e faz o commit no banco
                database.session.add(militar_agregado)
                database.session.commit()
            else:
                # Caso não exista publicação BG associada, você pode decidir o que fazer
                print("Publicação BG não encontrada para o militar agregado.")

        if situacao_selecionada and situacao_selecionada.condicao == 'À DISPOSIÇÃO':

            # Verifica se há uma publicação BG associada ao militar e à situação
            publicacao_situacao_bg = PublicacaoBg.query.filter_by(militar_id=militar.id,
                                                                  tipo_bg='situacao_militar').first()

            if publicacao_situacao_bg:
                # Criando o registro em 'militares_a_disposicao'
                militar_a_disposicao = MilitaresADisposicao(
                    militar_id=militar.id,
                    posto_grad_id=form_militar.posto_grad_id.data,
                    quadro_id=form_militar.quadro_id.data,
                    destino_id=form_militar.destino_id.data,
                    situacao_id=situacao_selecionada.id,
                    inicio_periodo=form_militar.inicio_periodo.data,
                    fim_periodo_disposicao=form_militar.fim_periodo.data,
                    publicacao_bg_id=publicacao_situacao_bg.id
                )

                militar_a_disposicao.atualizar_status()

                # Adiciona o registro de agregação e faz o commit no banco
                database.session.add(militar_a_disposicao)
                database.session.commit()
            else:
                flash('Publicação BG não encontrada para o militar à disposição.', 'alert-danger')

        if situacao_selecionada and situacao_selecionada.condicao == 'LICENÇA ESPECIAL':
            publicacao_situacao_bg = PublicacaoBg.query.filter_by(militar_id=militar.id,
                                                                  tipo_bg='situacao_militar').first()
            if publicacao_situacao_bg:
                militar_le = LicencaEspecial(
                    militar_id=militar.id,
                    posto_grad_id=form_militar.posto_grad_id.data,
                    quadro_id=form_militar.quadro_id.data,
                    destino_id=form_militar.destino_id.data,
                    situacao_id=situacao_selecionada.id,
                    inicio_periodo_le=form_militar.inicio_periodo.data,
                    fim_periodo_le=form_militar.fim_periodo.data,
                    publicacao_bg_id=publicacao_situacao_bg.id
                )

                militar_le.atualizar_status()

                database.session.add(militar_le)
                database.session.commit()
            else:
                flash('Publicação BG não encontrada para a Licença Especial.', 'alert-danger')

        if situacao_selecionada and situacao_selecionada.condicao == 'LTS':
            publicacao_situacao_bg = PublicacaoBg.query.filter_by(militar_id=militar.id,
                                                                  tipo_bg='situacao_militar').first()
            if publicacao_situacao_bg:
                militar_lts = LicencaParaTratamentoDeSaude(
                    militar_id=militar.id,
                    posto_grad_id=form_militar.posto_grad_id.data,
                    quadro_id=form_militar.quadro_id.data,
                    destino_id=form_militar.destino_id.data,
                    situacao_id=situacao_selecionada.id,
                    inicio_periodo_lts=form_militar.inicio_periodo.data,
                    fim_periodo_lts=form_militar.fim_periodo.data,
                    publicacao_bg_id=publicacao_situacao_bg.id
                )

                militar_lts.atualizar_status()

                database.session.add(militar_lts)
                database.session.commit()
            else:
                flash('Publicação BG não encontrada para LTS.', 'alert-danger')

        database.session.commit()

        flash('Militar adicionado com sucesso!', 'alert-success')
        return redirect(url_for('home'))

    return render_template('adicionar_militar.html', form_militar=form_militar)


@app.route('/verificar-arquivos', methods=['POST'])
@login_required
def verificar_arquivos():
    data = request.get_json()
    filenames = data.get('filenames', [])

    existing_files = []
    upload_folder = os.path.join(os.path.abspath(os.path.dirname(__file__)), app.config["UPLOAD_FOLDER"])

    for filename in filenames:
        file_path = os.path.join(upload_folder, secure_filename(filename))
        if os.path.exists(file_path):
            existing_files.append(filename)

    return jsonify({'exists': existing_files})


@app.route("/exibir-militar/<int:militar_id>", methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA')
def exibir_militar(militar_id):
    militar = Militar.query.get_or_404(militar_id)

    obm_funcao_tipo_1 = MilitarObmFuncao.query.filter_by(militar_id=militar_id, tipo=1) \
        .filter(MilitarObmFuncao.data_fim == None).first()

    obm_funcao_tipo_2 = MilitarObmFuncao.query.filter_by(militar_id=militar_id, tipo=2) \
        .filter(MilitarObmFuncao.data_fim == None).first()

    form_militar = FormMilitar(obj=militar)

    form_militar.funcao_gratificada_id.choices = [
        (funcao_gratificada.id, funcao_gratificada.gratificacao) for funcao_gratificada in FuncaoGratificada.query.all()
    ]
    form_militar.posto_grad_id.choices = [
        (posto.id, posto.sigla) for posto in PostoGrad.query.all()
    ]
    form_militar.quadro_id.choices = [
        (quadro.id, quadro.quadro) for quadro in Quadro.query.all()
    ]
    form_militar.localidade_id.choices = [
        (localidade_id.id, localidade_id.sigla) for localidade_id in Localidade.query.all()
    ]

    form_militar.obm_ids_1.choices = ([('', '-- Selecione uma opção --')] +
                                      [(obm.id, obm.sigla) for obm in Obm.query.all()])

    form_militar.funcao_ids_1.choices = ([('', '-- Selecione uma opção --')] +
                                         [(funcao.id, funcao.ocupacao) for funcao in Funcao.query.all()])

    form_militar.obm_ids_2.choices = ([('', '-- Selecione uma opção --')] +
                                      [(obm.id, obm.sigla) for obm in Obm.query.all()])

    form_militar.funcao_ids_2.choices = ([('', '-- Selecione uma opção --')] +
                                         [(funcao.id, funcao.ocupacao) for funcao in Funcao.query.all()])

    form_militar.situacao_id.choices = [
        (situacao.id, situacao.condicao) for situacao in Situacao.query.all()
    ]
    form_militar.estado_civil.choices = [
        (estado.id, estado.estado) for estado in EstadoCivil.query.all()
    ]
    form_militar.especialidade_id.choices = [
        (especialidade.id, especialidade.ocupacao) for especialidade in Especialidade.query.all()
    ]
    form_militar.destino_id.choices = [
        (destino.id, destino.local) for destino in Destino.query.all()
    ]
    form_militar.agregacoes_id.choices = [
        (agregacoes.id, agregacoes.tipo) for agregacoes in Agregacoes.query.all()
    ]
    form_militar.punicao_id.choices = [
        (punicao.id, punicao.sancao) for punicao in Punicao.query.all()
    ]
    form_militar.comportamento_id.choices = ([('', '-- Selecione uma opção --')] +
                                          [(comportamento.id, comportamento.conduta) for comportamento in
                                           Comportamento.query.all()
                                           ])

    if obm_funcao_tipo_1:
        form_militar.obm_ids_1.data = obm_funcao_tipo_1.obm_id
        form_militar.funcao_ids_1.data = obm_funcao_tipo_1.funcao_id

    if obm_funcao_tipo_2:
        form_militar.obm_ids_2.data = obm_funcao_tipo_2.obm_id
        form_militar.funcao_ids_2.data = obm_funcao_tipo_2.funcao_id

    form_militar.sexo.data = militar.sexo.name
    form_militar.raca.data = militar.raca.name

    # Calculando a idade do militar
    hoje = datetime.today().date()
    idade = hoje.year - militar.data_nascimento.year - (
            (hoje.month, hoje.day) < (militar.data_nascimento.month, militar.data_nascimento.day))
    form_militar.idade_atual.data = idade

    campos_bg = [
        'transferencia', 'situacao_militar', 'cfsd', 'cfc', 'cfs', 'cas',
        'choa', 'cfo', 'cbo', 'cao', 'csbm', 'soldado_tres',
        'soldado_dois', 'soldado_um', 'cabo', 'terceiro_sgt',
        'segundo_sgt', 'primeiro_sgt', 'subtenente',
        'publicidade_segundo_tenente', 'publicidade_primeiro_tenente',
        'pub_cap', 'pub_maj', 'pub_tc', 'pub_cel', 'pub_alteracao'
    ]

    # Recupera as publicações do BG e define campos para publicação do militar
    publicacoes_bg = PublicacaoBg.query.filter_by(militar_id=militar.id).all()

    # Inicializa todos os campos de publicações BG com valor vazio
    for campo in campos_bg:
        if hasattr(form_militar, campo):
            getattr(form_militar, campo).data = ""

    # Itera sobre as publicações do BG e verifica os campos
    for pub in publicacoes_bg:
        if pub.tipo_bg in campos_bg:
            if hasattr(form_militar, pub.tipo_bg):
                # Se o boletim_geral existir, utiliza o valor; caso contrário, mantém como vazio
                getattr(form_militar, pub.tipo_bg).data = pub.boletim_geral or ""

    if form_militar.validate_on_submit():
        form_militar.process(request.form)

        militar.nome_completo = form_militar.nome_completo.data
        militar.nome_guerra = form_militar.nome_guerra.data
        militar.cpf = form_militar.cpf.data
        militar.rg = form_militar.rg.data
        militar.nome_pai = form_militar.nome_pai.data
        militar.nome_mae = form_militar.nome_mae.data
        militar.matricula = form_militar.matricula.data
        militar.pis_pasep = form_militar.pis_pasep.data
        militar.num_titulo_eleitor = form_militar.num_titulo_eleitor.data
        militar.digito_titulo_eleitor = form_militar.digito_titulo_eleitor.data
        militar.zona = form_militar.zona.data
        militar.secao = form_militar.secao.data
        militar.posto_grad_id = form_militar.posto_grad_id.data
        militar.quadro_id = form_militar.quadro_id.data
        militar.localidade_id = form_militar.localidade_id.data
        militar.antiguidade = form_militar.antiguidade.data
        militar.sexo = form_militar.sexo.data
        militar.raca = form_militar.raca.data
        militar.data_nascimento = form_militar.data_nascimento.data
        militar.inclusao = form_militar.inclusao.data

        militar.completa_25_inclusao = datetime.strptime(str(form_militar.completa_25_inclusao.data),
                                                         '%Y-%m-%d').date() if form_militar.completa_25_inclusao.data else None
        militar.completa_30_inclusao = datetime.strptime(str(form_militar.completa_30_inclusao.data),
                                                         '%Y-%m-%d').date() if form_militar.completa_30_inclusao.data else None
        militar.completa_25_anos_sv = datetime.strptime(str(form_militar.completa_25_anos_sv.data),
                                                        '%Y-%m-%d').date() if form_militar.completa_25_anos_sv.data else None
        militar.completa_30_anos_sv = datetime.strptime(str(form_militar.completa_30_anos_sv.data),
                                                        '%Y-%m-%d').date() if form_militar.completa_30_anos_sv.data else None
        militar.inicio_periodo = datetime.strptime(str(form_militar.inicio_periodo.data),
                                                   '%Y-%m-%d').date() if form_militar.inicio_periodo.data else None
        militar.fim_periodo = datetime.strptime(str(form_militar.fim_periodo.data),
                                                '%Y-%m-%d').date() if form_militar.fim_periodo.data else None

        militar.punicao_id = form_militar.punicao_id.data
        militar.comportamento_id = form_militar.comportamento_id.data
        militar.efetivo_servico = form_militar.efetivo_servico.data
        militar.anos = form_militar.anos.data
        militar.meses = form_militar.meses.data
        militar.dias = form_militar.dias.data
        militar.total_dias = form_militar.total_dias.data
        militar.idade_reserva_grad = form_militar.idade_reserva_grad.data
        militar.estado_civil = form_militar.estado_civil.data
        militar.especialidade_id = form_militar.especialidade_id.data
        militar.pronto = form_militar.pronto.data
        militar.situacao_id = form_militar.situacao_id.data
        militar.agregacoes_id = form_militar.agregacoes_id.data
        militar.destino_id = form_militar.destino_id.data
        militar.inicio_periodo = form_militar.inicio_periodo.data
        militar.fim_periodo = form_militar.fim_periodo.data
        militar.ltip_afastamento_cargo_eletivo = form_militar.ltip_afastamento_cargo_eletivo.data
        militar.periodo_ltip = form_militar.periodo_ltip.data
        militar.total_ltip = form_militar.total_ltip.data
        militar.completa_25_anos_ltip = form_militar.completa_25_anos_ltip.data
        militar.completa_30_anos_ltip = form_militar.completa_30_anos_ltip.data
        militar.cursos = form_militar.cursos.data
        militar.grau_instrucao = form_militar.grau_instrucao.data
        militar.graduacao = form_militar.graduacao.data
        militar.pos_graduacao = form_militar.pos_graduacao.data
        militar.mestrado = form_militar.mestrado.data
        militar.doutorado = form_militar.doutorado.data
        militar.cfsd = form_militar.cfsd.data
        militar.cfc = form_militar.cfc.data
        militar.cfs = form_militar.cfs.data
        militar.cas = form_militar.cas.data
        militar.choa = form_militar.choa.data
        militar.cfo = form_militar.cfo.data
        militar.cbo = form_militar.cbo.data
        militar.cao = form_militar.cao.data
        militar.csbm = form_militar.csbm.data
        militar.cursos_civis = form_militar.cursos_civis.data
        militar.endereco = form_militar.endereco.data
        militar.complemento = form_militar.complemento.data
        militar.cidade = form_militar.cidade.data
        militar.estado = form_militar.estado.data
        militar.cep = form_militar.cep.data
        militar.celular = form_militar.celular.data
        militar.email = form_militar.email.data
        militar.inclusao_bg = form_militar.inclusao_bg.data
        militar.soldado_tres = form_militar.soldado_tres.data
        militar.soldado_dois = form_militar.soldado_dois.data
        militar.soldado_um = form_militar.soldado_um.data
        militar.cabo = form_militar.cabo.data
        militar.terceiro_sgt = form_militar.terceiro_sgt.data
        militar.segundo_sgt = form_militar.segundo_sgt.data
        militar.primeiro_sgt = form_militar.primeiro_sgt.data
        militar.subtenente = form_militar.subtenente.data
        militar.segundo_tenente = form_militar.segundo_tenente.data
        militar.primeiro_tenente = form_militar.primeiro_tenente.data
        militar.cap = form_militar.cap.data
        militar.maj = form_militar.maj.data
        militar.tc = form_militar.tc.data
        militar.cel = form_militar.cel.data
        militar.funcao_gratificada_id = form_militar.funcao_gratificada_id.data
        militar.alteracao_nome_guerra = form_militar.alteracao_nome_guerra.data

        # Verifica se OBM 1 e Função 1 foram modificadas ou removidas (selecionada opção vazia)
        if form_militar.obm_ids_1.data and form_militar.funcao_ids_1.data and form_militar.obm_ids_1.data != '' and form_militar.funcao_ids_1.data != '':
            # Somente faz a alteração se houver diferença entre os dados do banco e os do formulário
            obm_id_1 = int(form_militar.obm_ids_1.data)
            funcao_id_1 = int(form_militar.funcao_ids_1.data)

            if not obm_funcao_tipo_1 or (
                    obm_id_1 != obm_funcao_tipo_1.obm_id or funcao_id_1 != obm_funcao_tipo_1.funcao_id):
                # Feche o registro antigo se houver um
                if obm_funcao_tipo_1:
                    obm_funcao_tipo_1.data_fim = datetime.now()

                nova_relacao_1 = MilitarObmFuncao(
                    militar_id=militar_id,
                    obm_id=obm_id_1,
                    funcao_id=funcao_id_1,
                    tipo=1,
                    data_criacao=datetime.now(),
                    data_fim=None
                )
                database.session.add(nova_relacao_1)
        else:
            # Se a opção 'Selecione uma opção' foi escolhida, finalize a relação atual
            if obm_funcao_tipo_1:
                obm_funcao_tipo_1.data_fim = datetime.now()

        # Verifica se OBM 2 e Função 2 foram modificadas ou removidas
        if form_militar.obm_ids_2.data and form_militar.funcao_ids_2.data and form_militar.obm_ids_2.data != '' and form_militar.funcao_ids_2.data != '':
            # Somente faz a alteração se houver diferença entre os dados do banco e os do formulário
            obm_id_2 = int(form_militar.obm_ids_2.data)
            funcao_id_2 = int(form_militar.funcao_ids_2.data)

            if not obm_funcao_tipo_2 or (
                    obm_id_2 != obm_funcao_tipo_2.obm_id or funcao_id_2 != obm_funcao_tipo_2.funcao_id):
                # Feche o registro antigo se houver um
                if obm_funcao_tipo_2:
                    obm_funcao_tipo_2.data_fim = datetime.now()

                nova_relacao_2 = MilitarObmFuncao(
                    militar_id=militar_id,
                    obm_id=obm_id_2,
                    funcao_id=funcao_id_2,
                    tipo=2,
                    data_criacao=datetime.now(),
                    data_fim=None
                )
                database.session.add(nova_relacao_2)
        else:
            # Se a opção 'Selecione uma opção' foi escolhida, finalize a relação atual
            if obm_funcao_tipo_2:
                obm_funcao_tipo_2.data_fim = datetime.now()

        for campo_bg in campos_bg:
            if hasattr(form_militar, campo_bg):
                boletim_geral_data = getattr(form_militar, campo_bg).data
                if boletim_geral_data:
                    publicacao_existente = PublicacaoBg.query.filter_by(militar_id=militar.id, tipo_bg=campo_bg).first()
                    if publicacao_existente:
                        if publicacao_existente.boletim_geral != boletim_geral_data:
                            nova_publicacao = PublicacaoBg(
                                militar_id=militar.id,
                                tipo_bg=campo_bg,
                                boletim_geral=boletim_geral_data
                            )
                            database.session.add(nova_publicacao)
                    else:
                        nova_publicacao = PublicacaoBg(
                            militar_id=militar.id,
                            tipo_bg=campo_bg,
                            boletim_geral=boletim_geral_data
                        )
                        database.session.add(nova_publicacao)

        # Verifica se a situação selecionada é "AGREGADO"
        situacao_selecionada = Situacao.query.get(form_militar.situacao_id.data)
        if situacao_selecionada and situacao_selecionada.condicao == 'AGREGADO':

            # Verifica se há uma publicação BG associada ao militar e à situação
            publicacao_situacao_bg = PublicacaoBg.query.filter_by(
                militar_id=militar.id,
                tipo_bg='situacao_militar'
            ).first()

            if publicacao_situacao_bg:
                # Verifica se o militar já está na tabela 'militares_agregados'
                militar_agregado = MilitaresAgregados.query.filter_by(militar_id=militar.id).first()

                if militar_agregado:
                    # Atualiza o registro existente
                    militar_agregado.posto_grad_id = form_militar.posto_grad_id.data
                    militar_agregado.quadro_id = form_militar.quadro_id.data
                    militar_agregado.destino_id = form_militar.destino_id.data
                    militar_agregado.situacao_id = situacao_selecionada.id
                    militar_agregado.inicio_periodo = form_militar.inicio_periodo.data
                    militar_agregado.fim_periodo_agregacao = form_militar.fim_periodo.data
                    militar_agregado.publicacao_bg_id = publicacao_situacao_bg.id
                else:
                    # Cria um novo registro
                    militar_agregado = MilitaresAgregados(
                        militar_id=militar.id,
                        posto_grad_id=form_militar.posto_grad_id.data,
                        quadro_id=form_militar.quadro_id.data,
                        destino_id=form_militar.destino_id.data,
                        situacao_id=situacao_selecionada.id,
                        inicio_periodo=form_militar.inicio_periodo.data,
                        fim_periodo_agregacao=form_militar.fim_periodo.data,
                        publicacao_bg_id=publicacao_situacao_bg.id
                    )
                    database.session.add(militar_agregado)

                # Atualiza o status e faz o commit no banco
                militar_agregado.atualizar_status()
                database.session.commit()
            else:
                print("Publicação BG não encontrada para o militar agregado.")
                flash("Publicação BG não encontrada para o militar agregado.", "alert-danger")

        # Verifica se a situação selecionada é "À DISPOSIÇÃO"
        if situacao_selecionada and situacao_selecionada.condicao == 'À DISPOSIÇÃO':

            # Verifica se há uma publicação BG associada ao militar e à situação
            publicacao_situacao_bg = PublicacaoBg.query.filter_by(
                militar_id=militar.id,
                tipo_bg='situacao_militar'
            ).first()

            if publicacao_situacao_bg:
                # Verifica se o militar já está na tabela 'militares_a_disposicao'
                militar_a_disposicao = MilitaresADisposicao.query.filter_by(militar_id=militar.id).first()

                if militar_a_disposicao:
                    # Atualiza o registro existente
                    militar_a_disposicao.posto_grad_id = form_militar.posto_grad_id.data
                    militar_a_disposicao.quadro_id = form_militar.quadro_id.data
                    militar_a_disposicao.destino_id = form_militar.destino_id.data
                    militar_a_disposicao.situacao_id = situacao_selecionada.id
                    militar_a_disposicao.inicio_periodo = form_militar.inicio_periodo.data
                    militar_a_disposicao.fim_periodo_disposicao = form_militar.fim_periodo.data
                    militar_a_disposicao.publicacao_bg_id = publicacao_situacao_bg.id
                else:
                    # Cria um novo registro
                    militar_a_disposicao = MilitaresADisposicao(
                        militar_id=militar.id,
                        posto_grad_id=form_militar.posto_grad_id.data,
                        quadro_id=form_militar.quadro_id.data,
                        destino_id=form_militar.destino_id.data,
                        situacao_id=situacao_selecionada.id,
                        inicio_periodo=form_militar.inicio_periodo.data,
                        fim_periodo_disposicao=form_militar.fim_periodo.data,
                        publicacao_bg_id=publicacao_situacao_bg.id
                    )
                    database.session.add(militar_a_disposicao)

                # Atualiza o status e faz o commit no banco
                militar_a_disposicao.atualizar_status()
                database.session.commit()
            else:
                flash("Publicação BG não encontrada para o militar à disposição.", "alert-danger")

        if situacao_selecionada and situacao_selecionada.condicao == 'LICENÇA ESPECIAL':
            publicacao_situacao_bg = PublicacaoBg.query.filter_by(militar_id=militar.id,
                                                                  tipo_bg='situacao_militar').first()

            if publicacao_situacao_bg:
                militar_le = LicencaEspecial.query.filter_by(militar_id=militar.id).first()

                if militar_le:
                    militar_le.posto_grad_id = form_militar.posto_grad_id.data
                    militar_le.quadro_id = form_militar.quadro_id.data
                    militar_le.destino_id = form_militar.destino_id.data
                    militar_le.situacao_id = situacao_selecionada.id
                    militar_le.inicio_periodo_le = form_militar.inicio_periodo.data
                    militar_le.fim_periodo_le = form_militar.fim_periodo.data
                    militar_le.publicacao_bg_id = publicacao_situacao_bg.id

                else:
                    militar_le = LicencaEspecial(
                        militar_id=militar.id,
                        posto_grad_id=form_militar.posto_grad_id.data,
                        quadro_id=form_militar.quadro_id.data,
                        destino_id=form_militar.destino_id.data,
                        situacao_id=situacao_selecionada.id,
                        inicio_periodo_le=form_militar.inicio_periodo.data,
                        fim_periodo_le=form_militar.fim_periodo.data,
                        publicacao_bg_id=publicacao_situacao_bg.id
                    )
                    database.session.add(militar_le)

                militar_le.atualizar_status()
                database.session.commit()
            else:
                flash("Publicação BG não encontrada para a Licença Especial.", "alert-danger")

        if situacao_selecionada and situacao_selecionada.condicao == 'LTS':
            publicacao_situacao_bg = PublicacaoBg.query.filter_by(militar_id=militar.id,
                                                                  tipo_bg='situacao_militar').first()

            if publicacao_situacao_bg:
                militar_lts = LicencaParaTratamentoDeSaude.query.filter_by(militar_id=militar.id).first()

                if militar_lts:
                    militar_lts.posto_grad_id = form_militar.posto_grad_id.data
                    militar_lts.quadro_id = form_militar.quadro_id.data
                    militar_lts.destino_id = form_militar.destino_id.data
                    militar_lts.situacao_id = situacao_selecionada.id
                    militar_lts.inicio_periodo_lts = form_militar.inicio_periodo.data
                    militar_lts.fim_periodo_lts = form_militar.fim_periodo.data
                    militar_lts.publicacao_bg_id = publicacao_situacao_bg.id

                else:
                    militar_lts = LicencaParaTratamentoDeSaude(
                        militar_id=militar.id,
                        posto_grad_id=form_militar.posto_grad_id.data,
                        quadro_id=form_militar.quadro_id.data,
                        destino_id=form_militar.destino_id.data,
                        situacao_id=situacao_selecionada.id,
                        inicio_periodo_lts=form_militar.inicio_periodo.data,
                        fim_periodo_lts=form_militar.fim_periodo.data,
                        publicacao_bg_id=publicacao_situacao_bg.id
                    )
                    database.session.add(militar_lts)

                militar_lts.atualizar_status()
                database.session.commit()
            else:
                flash("Publicação BG não encontrada para a LTS.", "alert-danger")

        try:
            database.session.commit()
            flash('Militar atualizado com sucesso!', 'alert-success')
            return redirect(url_for('militares', militar_id=militar_id))
        except Exception as e:
            database.session.rollback()
            flash(f'Erro ao atualizar o Militar. Tente novamente. {e}', 'alert-danger')

    return render_template('exibir_militar.html', form_militar=form_militar,
                           militar=militar)


@app.route("/api/militares", methods=['GET'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH')
def api_militares():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    nome_completo = request.args.get('nome_completo', '', type=str)
    posto_grad_id = request.args.get('posto_grad_id', '', type=int)
    especialidade_id = request.args.get('especialidade_id', '', type=int)
    quadro_id = request.args.get('quadro_id', '', type=int)
    situacao_id = request.args.get('situacao_id', '', type=int)
    agregacoes_id = request.args.get('agregacoes_id', '', type=int)
    destino_id = request.args.get('destino_id', '', type=int)
    localidade_id = request.args.get('localidade_id', '', type=int)
    matricula = request.args.get('matricula', '', type=str)

    query = Militar.query

    if search:
        query = query.filter(Militar.nome_completo.ilike(f"%{search}%"))
    if nome_completo:
        query = query.filter(Militar.nome_completo.ilike(f'%{nome_completo}%'))
    if posto_grad_id:
        query = query.filter(Militar.posto_grad_id == posto_grad_id)
    if especialidade_id:
        query = query.filter(Militar.especialidade_id == especialidade_id)
    if quadro_id:
        query = query.filter(Militar.quadro_id == quadro_id)
    if situacao_id:
        query = query.filter(Militar.situacao_id == situacao_id)
    if agregacoes_id:
        query = query.filter(Militar.agregacoes_id == agregacoes_id)
    if destino_id:
        query = query.filter(Militar.destino_id == destino_id)
    if localidade_id:
        query = query.filter(Militar.localidade_id == localidade_id)
    if matricula:
        query = query.filter(Militar.matricula == matricula)

    militares_paginados = query.paginate(page=page, per_page=10)

    militares = []
    for militar in militares_paginados.items:
        # Consultas adicionais para buscar as informações relacionadas
        especialidade = Especialidade.query.get(militar.especialidade_id)
        posto_grad = PostoGrad.query.get(militar.posto_grad_id)
        quadro = Quadro.query.get(militar.quadro_id)
        situacao = Situacao.query.get(militar.situacao_id)
        agregacoes = Agregacoes.query.get(militar.agregacoes_id)
        destino = Destino.query.get(militar.destino_id)
        localidade = Localidade.query.get(militar.localidade_id)

        # Filtrar apenas as relações OBM + Função ativas (sem data_fim)
        obm_funcoes_ativas = MilitarObmFuncao.query.filter_by(militar_id=militar.id).filter(
            MilitarObmFuncao.data_fim == None
        ).all()

        # Coletar as siglas das OBMs e ocupações das Funções ativas, garantindo que não ocorra erro se OBM ou Função for None
        obms_ativas = [Obm.query.get(of.obm_id).sigla if Obm.query.get(of.obm_id) else 'OBM não encontrada' for of in
                       obm_funcoes_ativas]
        funcoes_ativas = [
            Funcao.query.get(of.funcao_id).ocupacao if Funcao.query.get(of.funcao_id) else 'Função não encontrada' for
            of in obm_funcoes_ativas]

        militares.append({
            'id': militar.id,
            'nome_completo': militar.nome_completo,
            'nome_guerra': militar.nome_guerra,
            'especialidade': especialidade.ocupacao if especialidade else None,
            'cpf': militar.cpf,
            'rg': militar.rg,
            'posto_grad_sigla': posto_grad.sigla if posto_grad else None,  # Sigla do posto/graduação
            'obms': obms_ativas,  # Siglas das OBMs ativas
            'funcoes': funcoes_ativas,  # Descrições das funções ativas
            'quadro': quadro.quadro if quadro else None,  # Nome do quadro
            'situacao': situacao.condicao if situacao else None,  # Nome da situação
            'agregacoes': agregacoes.tipo if agregacoes else None,  # Nome da agregação
            'destino': destino.local if destino else None,  # Nome do destino
            'localidade': localidade.sigla if localidade else None,
            'matricula': militar.matricula
        })

    return jsonify({
        'militares': militares,
        'has_next': militares_paginados.has_next,
        'has_prev': militares_paginados.has_prev,
        'next_page': militares_paginados.next_num,
        'prev_page': militares_paginados.prev_num,
        'page': militares_paginados.page
    })


@app.route("/militares", methods=['GET'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH')
def militares():
    form_militar = FormMilitar()

    form_militar.obm_ids_1.choices = [
                                         ('', '-- Selecione OBM --')
                                     ] + [(obm.id, obm.sigla) for obm in Obm.query.all()]
    form_militar.obm_ids_2.choices = [
                                         ('', '-- Selecione OBM --')
                                     ] + [(obm.id, obm.sigla) for obm in Obm.query.all()]
    form_militar.posto_grad_id.choices = [
                                             ('', '-- Selecione Posto/Grad --')
                                         ] + [(posto.id, posto.sigla) for posto in PostoGrad.query.all()]
    form_militar.quadro_id.choices = [
                                         ('', '-- Selecione Quadro --')
                                     ] + [(quadro.id, quadro.quadro) for quadro in Quadro.query.all()]
    form_militar.especialidade_id.choices = [
                                                ('', '-- Selecione Especialidade --')
                                            ] + [(especialidade.id, especialidade.ocupacao) for especialidade in
                                                 Especialidade.query.all()]
    form_militar.localidade_id.choices = [
                                             ('', '-- Selecione Localidade --')
                                         ] + [(localidade.id, localidade.sigla) for localidade in
                                              Localidade.query.all()]
    form_militar.situacao_id.choices = [
                                           ('', '-- Selecione Situação --')
                                       ] + [(situacao.id, situacao.condicao) for situacao in Situacao.query.all()]
    form_militar.funcao_ids_1.choices = [
                                            ('', '-- Selecione Função --')] + [(funcao.id, funcao.ocupacao) for
                                                                               funcao in Funcao.query.all()]

    return render_template('militares.html', form_militar=form_militar)


@app.route('/tabela-militares', methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA')
def tabela_militares():
    try:
        militares_filtrados = []

        if request.method == 'POST':
            # Recebendo dados do formulário
            obm_id = request.form.get('obm_ids_1')  # Captura apenas um único ID de OBM
            posto_grad_id = request.form.get('posto_grad_id')
            quadro_id = request.form.get('quadro_id')
            especialidade = request.form.get('especialidade_id')
            localidade = request.form.get('localidade_id')
            situacao_id = request.form.get('situacao_id')
            funcao_id = request.form.get('funcao_ids_1')

            # Aliases para MilitarObmFuncao
            militar_obm_funcao_obm = aliased(MilitarObmFuncao)
            militar_obm_funcao_funcao = aliased(MilitarObmFuncao)

            # Iniciar a query base
            query = Militar.query

            # Filtrar por OBM
            if obm_id:
                query = query.join(militar_obm_funcao_obm).filter(
                    militar_obm_funcao_obm.obm_id == obm_id,
                    militar_obm_funcao_obm.data_fim == None  # Filtra OBMs ativas
                )

            # Filtrar por função
            if funcao_id:
                query = query.join(militar_obm_funcao_funcao).filter(
                    militar_obm_funcao_funcao.funcao_id == funcao_id,
                    militar_obm_funcao_funcao.data_fim == None
                )

            # Filtrar por outras condições
            if posto_grad_id:
                query = query.filter(Militar.posto_grad_id == posto_grad_id)
            if quadro_id:
                query = query.filter(Militar.quadro_id == quadro_id)
            if especialidade:
                query = query.filter(Militar.especialidade_id == especialidade)
            if localidade:
                query = query.filter(Militar.localidade_id == localidade)
            if situacao_id:
                query = query.filter(Militar.situacao_id == situacao_id)

            query = query.distinct()  # Evitar duplicações
            militares_filtrados = query.all()

            # Limpar a sessão antes de armazenar novos dados
            session['militares_filtrados'] = []

            # Adicionando OBMs e funções ativas aos militares
            for militar in militares_filtrados:
                # Filtrar apenas as relações OBM + Função ativas (sem data_fim)
                obm_funcoes_ativas = MilitarObmFuncao.query.filter_by(militar_id=militar.id).filter(
                    MilitarObmFuncao.data_fim == None
                ).all()

                # Coletar as siglas das OBMs e ocupações das Funções ativas
                obms_ativas = [Obm.query.get(of.obm_id).sigla if Obm.query.get(of.obm_id) else 'OBM não encontrada' for
                               of in obm_funcoes_ativas]
                funcoes_ativas = [Funcao.query.get(of.funcao_id).ocupacao if Funcao.query.get(
                    of.funcao_id) else 'Função não encontrada' for of in obm_funcoes_ativas]

                militar.obms = obms_ativas
                militar.funcoes = funcoes_ativas

                militar.posto_grad = PostoGrad.query.get(
                    militar.posto_grad_id).sigla if militar.posto_grad_id else 'Posto/Graduação não encontrada'
                militar.quadro = Quadro.query.get(
                    militar.quadro_id).quadro if militar.quadro_id else 'Quadro não encontrado'
                militar.especialidade = Especialidade.query.get(
                    militar.especialidade_id).ocupacao if militar.especialidade_id else 'Especialidade não encontrada'
                militar.localidade = Localidade.query.get(
                    militar.localidade_id).sigla if militar.localidade_id else 'Localidade não encontrada'
                militar.situacao = Situacao.query.get(
                    militar.situacao_id).condicao if militar.situacao_id else 'Situação não encontrada'

                militar_info = {
                    'Nome Completo': militar.nome_completo,
                    'Nome de Guerra': militar.nome_guerra,
                    'CPF': militar.cpf,
                    'RG': militar.rg,
                    'Matrícula': militar.matricula,
                    'Posto/Graduação': PostoGrad.query.get(
                        militar.posto_grad_id).sigla if militar.posto_grad_id else 'N/A',
                    'Quadro': Quadro.query.get(militar.quadro_id).quadro if militar.quadro_id else 'N/A',
                    'Especialidade': Especialidade.query.get(
                        militar.especialidade_id).ocupacao if militar.especialidade_id else 'N/A',
                    'Localidade': Localidade.query.get(militar.localidade_id).sigla if militar.localidade_id else 'N/A',
                    'Situação': Situacao.query.get(militar.situacao_id).condicao if militar.situacao_id else 'N/A',
                    'OBM 1': obms_ativas[0] if len(obms_ativas) > 0 else 'N/A',
                    'Função 1': funcoes_ativas[0] if len(funcoes_ativas) > 0 else 'N/A',
                    'OBM 2': obms_ativas[1] if len(obms_ativas) > 1 else 'N/A',
                    'Função 2': funcoes_ativas[1] if len(funcoes_ativas) > 1 else 'N/A'
                }
                if 'militares_filtrados' not in session:
                    session['militares_filtrados'] = []
                session['militares_filtrados'].append(militar_info)

        return render_template('relacao_militares.html', militares=militares_filtrados)

    except Exception as e:
        print(f"Erro ao processar a requisição: {e}")
        return jsonify({'error': 'Ocorreu um erro ao processar a requisição.'}), 500


@app.route("/export-excel", methods=["GET"])
@login_required
def export_excel():
    try:
        if 'militares_filtrados' not in session:
            return jsonify({'error': 'Nenhum dado filtrado disponível para download.'}), 400

        dados = session['militares_filtrados']
        df = pd.DataFrame(dados)

        # Definindo a ordem das colunas (ajuste conforme necessário)
        colunas_em_ordem = [
            'Nome Completo',
            'Nome de Guerra',
            'CPF',
            'RG',
            'Matrícula',
            'Posto/Graduação',
            'Quadro',
            'Especialidade',
            'Localidade',
            'Situação',
            'OBM 1',
            'Função 1',
            'OBM 2',
            'Função 2'
        ]

        # Reordenando o DataFrame de acordo com a lista definida
        df = df[colunas_em_ordem]

        # Salva para um arquivo Excel na memória
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')

        # Converter o DataFrame para um Excel
        df.to_excel(writer, index=False, sheet_name='Militares')

        # Acessar o workbook e a planilha
        workbook = writer.book
        worksheet = writer.sheets['Militares']

        # Definindo a largura das colunas
        column_widths = {
            'A': 25,  # Nome Completo
            'B': 25,  # Nome de Guerra
            'C': 15,  # CPF
            'D': 15,  # RG
            'E': 30,  # Matrícula
            'F': 20,  # Posto/Graduação
            'G': 30,  # Quadro
            'H': 30,  # 'Especialidade'
            'I': 20,  # Localidade
            'J': 20,  # Situação
            'K': 20,  # OBM 1
            'L': 20,  # Função 1
            'M': 20,  # OBM 2
            'N': 20  # Função 2
        }

        for col, width in column_widths.items():
            worksheet.set_column(f'{col}:{col}', width)

        # Estilizando o cabeçalho
        header_format = workbook.add_format({
            'bg_color': '#00008b',  # Cor de fundo azul
            'font_color': '#FFFFFF',  # Cor da fonte branca
            'bold': True,  # Texto em negrito
            'border': 1  # Bordas
        })

        # Aplicar o formato ao cabeçalho
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        writer.close()
        output.seek(0)

        return send_file(output, download_name="militares_filtrados.xlsx", as_attachment=True)

    except Exception as e:
        print(f"Erro ao processar a requisição: {e}")
        return jsonify({'error': 'Ocorreu um erro ao processar a requisição.'}), 500


@app.route("/militares-a-disposicao")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH')
def militares_a_disposicao():
    militares_a_disposicao = MilitaresADisposicao.query.all()

    return render_template('militares_a_disposicao.html', militares=militares_a_disposicao)


@app.route("/militares-agregados")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH')
def militares_agregados():
    militares_agregados = MilitaresAgregados.query.all()

    return render_template('militares_agregados.html', militares=militares_agregados)


@app.route("/licenca-especial")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH')
def licenca_especial():
    militares_le = LicencaEspecial.query.all()

    return render_template('licenca_especial.html', militares_le=militares_le)


@app.route("/licenca-para-tratamento-de-saude")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH')
def lts():
    militares_lts = LicencaParaTratamentoDeSaude.query.all()

    return render_template('licenca_para_tratamento_de_saude.html', militares_lts=militares_lts)


@app.route("/exportar-excel/<string:tabela>")
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA', 'DRH')
def exportar_excel(tabela):
    # Mapeamento das tabelas para consultas
    tabela_mapping = {
        'militares_agregados': {
            'model': MilitaresAgregados,
            'columns': [
                'posto_grad.sigla', 'quadro.quadro', 'militar.nome_completo',
                'destino.local', 'situacao.condicao', 'inicio_periodo',
                'fim_periodo_agregacao', 'status', 'publicacao_bg.boletim_geral'
            ]
        },
        'militares_a_disposicao': {
            'model': MilitaresADisposicao,
            'columns': [
                'posto_grad.sigla', 'quadro.quadro', 'militar.nome_completo',
                'destino.local', 'situacao.condicao', 'inicio_periodo',
                'fim_periodo_disposicao', 'status', 'publicacao_bg.boletim_geral'
            ]
        }
    }

    # Verifica se a tabela especificada está no mapeamento
    if tabela not in tabela_mapping:
        return jsonify({'error': 'Tabela não encontrada'}), 404

    # Obter modelo e colunas da tabela especificada
    tabela_info = tabela_mapping[tabela]
    modelo = tabela_info['model']
    colunas = tabela_info['columns']

    # Consultar os dados da tabela
    dados = modelo.query.all()

    # Construir dados para o DataFrame do Pandas
    export_data = []
    for item in dados:
        export_row = {
            'Posto/Graduação': getattr(item.posto_grad, 'sigla', 'N/A'),
            'Quadro': getattr(item.quadro, 'quadro', 'N/A'),
            'Nome Completo': getattr(item.militar, 'nome_completo', 'N/A'),
            'Destino': getattr(item.destino, 'local', 'N/A'),
            'Situação': getattr(item.situacao, 'condicao', 'N/A'),
            'A contar de': item.inicio_periodo.strftime('%d/%m/%Y') if item.inicio_periodo else 'N/A',
            'Término': (
                item.fim_periodo_agregacao.strftime('%d/%m/%Y') if tabela == 'militares_agregados' else
                item.fim_periodo_disposicao.strftime('%d/%m/%Y') if item.fim_periodo_disposicao else 'N/A'
            ),
            'Status': item.status,
            'Documento Autorizador': getattr(item.publicacao_bg, 'boletim_geral', 'N/A')
        }
        export_data.append(export_row)

    # Criar DataFrame
    df = pd.DataFrame(export_data)

    # Gerar arquivo Excel em memória
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados')
        workbook = writer.book
        worksheet = writer.sheets['Dados']

        # Definir formatos personalizados
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#1F4E78',  # Azul escuro
            'font_color': 'white',
            'align': 'center',
            'valign': 'vcenter'
        })

        cell_centered_format = workbook.add_format({'align': 'center', 'valign': 'vcenter'})
        cell_left_format = workbook.add_format({'align': 'left', 'valign': 'vcenter'})

        # Ajustar largura das colunas
        column_widths = {
            'Posto/Graduação': 15,
            'Quadro': 15,
            'Nome Completo': 30,
            'Destino': 20,
            'Situação': 15,
            'A contar de': 12,
            'Término': 12,
            'Status': 15,
            'Documento Autorizador': 30
        }

        # Aplicar largura das colunas e formatação
        for col_num, column_title in enumerate(df.columns):
            width = column_widths.get(column_title, 15)  # Valor padrão 15
            worksheet.set_column(col_num, col_num, width)

            # Aplicar estilo ao cabeçalho
            worksheet.write(0, col_num, column_title, header_format)

            # Aplicar centralização condicional para colunas específicas
            if column_title in ['Nome Completo', 'Documento Autorizador']:
                worksheet.set_column(col_num, col_num, width, cell_left_format)
            else:
                worksheet.set_column(col_num, col_num, width, cell_centered_format)

    output.seek(0)

    # Enviar arquivo Excel para download
    nome_arquivo = f'{tabela}.xlsx'
    return send_file(output, as_attachment=True, download_name=nome_arquivo,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route("/usuarios", methods=['GET'])
@login_required
@checar_ocupacao('DIRETOR')
def usuarios():
    page = request.args.get('page', 1, type=int)
    usuarios = User.query \
        .join(FuncaoUser, User.funcao_user_id == FuncaoUser.id) \
        .add_columns(User.nome, User.cpf, User.id,
                     FuncaoUser.ocupacao.label('funcao_ocupacao')) \
        .paginate(page=page, per_page=10)
    return render_template('usuarios.html', usuarios=usuarios)


@app.route('/usuario/<int:id_usuario>', methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR')
def exibir_usuario(id_usuario):
    # Carregar o usuário diretamente
    usuario = User.query.get_or_404(id_usuario)

    # Carregar informações extras sobre a função com join para exibição na tabela
    usuario_info = User.query \
        .join(FuncaoUser, User.funcao_user_id == FuncaoUser.id) \
        .add_columns(User.nome, User.cpf, User.id, User.email,
                     FuncaoUser.ocupacao.label('funcao_ocupacao')) \
        .filter(User.id == id_usuario) \
        .first_or_404()

    form = FormCriarUsuario(obj=usuario)
    form.current_user_id = id_usuario
    form.funcao_user_id.choices = [(funcao.id, funcao.ocupacao) for funcao in FuncaoUser.query.all()]

    if form.validate_on_submit():
        usuario.nome = form.nome.data
        usuario.email = form.email.data
        usuario.cpf = form.cpf.data
        usuario.funcao_user_id = form.funcao_user_id.data

        if form.senha.data:
            usuario.senha = bcrypt.generate_password_hash(form.senha.data).decode('utf-8')

        try:
            database.session.commit()
            flash('Usuário atualizado com sucesso!', 'alert-success')
            return redirect(url_for('usuarios', id_usuario=id_usuario))
        except Exception as e:
            database.session.rollback()
            flash(f'Erro ao atualizar o usuário. Tente novamente. {e}', 'alert-danger')

    return render_template('usuario_detalhes.html', usuario=usuario_info, form=form)


@app.route('/usuario/<usuario_id>/excluir', methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR')
def excluir_usuario(usuario_id):
    usuario = User.query.get(usuario_id)
    database.session.delete(usuario)
    database.session.commit()
    flash('Usuário excluído permanentemente', 'alert-danger')
    return redirect(url_for('usuarios'))


@app.route('/militar/<int:militar_id>/excluir', methods=['GET', 'POST'])
@login_required
@checar_ocupacao('DIRETOR', 'CHEFE', 'MAPA DA FORÇA')
def excluir_militar(militar_id):
    militar = Militar.query.get(militar_id)
    database.session.delete(militar)
    database.session.commit()
    flash('Militar excluído permanentemente', 'alert-danger')
    return redirect(url_for('militares'))


@app.route('/sair')
@login_required
def sair():
    logout_user()
    flash('Faça o Login para continuar', 'alert-success')
    return redirect(url_for('login'))
