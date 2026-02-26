from flask import Flask, render_template, request, redirect, session
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# banco
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    import psycopg2
else:
    import sqlite3

app = Flask(__name__)
app.secret_key = "chave_secreta_simples"

ADMIN_SENHA = "1234"

# timezone Brasília
BRASILIA = ZoneInfo("America/Sao_Paulo")


# -----------------------
# CONEXÃO BANCO
# -----------------------
def get_conn():

    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)

    else:
        return sqlite3.connect("banco.db")


# -----------------------
# CRIAR BANCO
# -----------------------
def criar_banco():

    conn = get_conn()
    c = conn.cursor()

    if DATABASE_URL:

        c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nome TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS ponto (
            id SERIAL PRIMARY KEY,
            funcionario TEXT,
            data TEXT,
            entrada TEXT,
            saida_almoco TEXT,
            volta_almoco TEXT,
            saida_final TEXT,
            horas REAL,
            horas_extras REAL
        )
        """)

    else:

        c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS ponto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            funcionario TEXT,
            data TEXT,
            entrada TEXT,
            saida_almoco TEXT,
            volta_almoco TEXT,
            saida_final TEXT,
            horas REAL,
            horas_extras REAL
        )
        """)

    c.execute("SELECT COUNT(*) FROM usuarios")

    if c.fetchone()[0] == 0:

        c.execute("INSERT INTO usuarios (nome) VALUES ('João')")
        c.execute("INSERT INTO usuarios (nome) VALUES ('Maria')")
        c.execute("INSERT INTO usuarios (nome) VALUES ('Carlos')")

    conn.commit()
    conn.close()


criar_banco()


# -----------------------
# LOGIN
# -----------------------
@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        session.clear()

    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT nome FROM usuarios")
    usuarios = c.fetchall()

    erro = None

    if request.method == "POST":

        senha_admin = request.form.get("admin_senha", "").strip()
        usuario = request.form.get("usuario", "").strip()

        if senha_admin:

            if senha_admin == ADMIN_SENHA:

                session["usuario"] = "ADMIN"
                conn.close()
                return redirect("/relatorio")

            else:
                erro = "Senha inválida"

        elif usuario:

            session["usuario"] = usuario
            conn.close()
            return redirect("/home")

    conn.close()

    return render_template("login.html", usuarios=usuarios, erro=erro)


# -----------------------
# HOME
# -----------------------
@app.route("/home")
def home():

    if "usuario" not in session:
        return redirect("/")

    if session["usuario"] == "ADMIN":
        return redirect("/relatorio")

    usuario = session["usuario"]

    data = datetime.now(BRASILIA).strftime("%d/%m/%Y")

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        SELECT data, entrada, saida_almoco, volta_almoco,
               saida_final, horas, horas_extras
        FROM ponto
        WHERE funcionario = %s
        ORDER BY id DESC
    """ if DATABASE_URL else """
        SELECT data, entrada, saida_almoco, volta_almoco,
               saida_final, horas, horas_extras
        FROM ponto
        WHERE funcionario = ?
        ORDER BY id DESC
    """, (usuario,))

    dados = c.fetchall()

    c.execute("""
        SELECT COALESCE(SUM(horas),0)
        FROM ponto
        WHERE funcionario = %s
    """ if DATABASE_URL else """
        SELECT COALESCE(SUM(horas),0)
        FROM ponto
        WHERE funcionario = ?
    """, (usuario,))

    total = round(float(c.fetchone()[0]), 2)

    c.execute("""
        SELECT entrada, saida_almoco, volta_almoco, saida_final
        FROM ponto
        WHERE funcionario=%s AND data=%s
        ORDER BY id DESC LIMIT 1
    """ if DATABASE_URL else """
        SELECT entrada, saida_almoco, volta_almoco, saida_final
        FROM ponto
        WHERE funcionario=? AND data=?
        ORDER BY id DESC LIMIT 1
    """, (usuario, data))

    row = c.fetchone()

    if not row:
        proxima = "Bater Entrada"

    else:

        e, sa, va, sf = row

        if e and not sa:
            proxima = "Saída Almoço"

        elif sa and not va:
            proxima = "Volta Almoço"

        elif va and not sf:
            proxima = "Saída Final"

        else:
            proxima = "Nova Entrada"

    conn.close()

    return render_template(
        "index.html",
        usuario=usuario,
        data=data,
        dados=dados,
        total=total,
        proxima=proxima
    )


# -----------------------
# BATER PONTO
# -----------------------
@app.route("/bater", methods=["POST"])
def bater():

    if session.get("usuario") in (None, "ADMIN"):
        return redirect("/")

    usuario = session["usuario"]

    agora = datetime.now(BRASILIA).strftime("%H:%M")
    data = datetime.now(BRASILIA).strftime("%d/%m/%Y")

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        SELECT id, entrada, saida_almoco, volta_almoco, saida_final
        FROM ponto
        WHERE funcionario=%s AND data=%s
        ORDER BY id DESC LIMIT 1
    """ if DATABASE_URL else """
        SELECT id, entrada, saida_almoco, volta_almoco, saida_final
        FROM ponto
        WHERE funcionario=? AND data=?
        ORDER BY id DESC LIMIT 1
    """, (usuario, data))

    row = c.fetchone()

    if not row:

        c.execute("""
            INSERT INTO ponto
            (funcionario,data,entrada)
            VALUES (%s,%s,%s)
        """ if DATABASE_URL else """
            INSERT INTO ponto
            (funcionario,data,entrada)
            VALUES (?,?,?)
        """, (usuario, data, agora))

    else:

        pid, e, sa, va, sf = row

        if e and not sa:

            c.execute(
                "UPDATE ponto SET saida_almoco=%s WHERE id=%s"
                if DATABASE_URL else
                "UPDATE ponto SET saida_almoco=? WHERE id=?",
                (agora, pid)
            )

        elif sa and not va:

            c.execute(
                "UPDATE ponto SET volta_almoco=%s WHERE id=%s"
                if DATABASE_URL else
                "UPDATE ponto SET volta_almoco=? WHERE id=?",
                (agora, pid)
            )

        elif va and not sf:

            def min(h):
                t = datetime.strptime(h, "%H:%M")
                return t.hour*60+t.minute

            total_min = (min(sa)-min(e))+(min(agora)-min(va))
            horas = round(total_min/60,2)

            horas_extras = round(horas-8,2) if horas>8 else 0

            c.execute("""
                UPDATE ponto
                SET saida_final=%s, horas=%s, horas_extras=%s
                WHERE id=%s
            """ if DATABASE_URL else """
                UPDATE ponto
                SET saida_final=?, horas=?, horas_extras=?
                WHERE id=?
            """,(agora, horas, horas_extras, pid))

        else:

            c.execute("""
                INSERT INTO ponto
                (funcionario,data,entrada)
                VALUES (%s,%s,%s)
            """ if DATABASE_URL else """
                INSERT INTO ponto
                (funcionario,data,entrada)
                VALUES (?,?,?)
            """,(usuario,data,agora))

    conn.commit()
    conn.close()

    return redirect("/home")


# -----------------------
# RELATORIO
# -----------------------
@app.route("/relatorio")
def relatorio():

    if session.get("usuario")!="ADMIN":
        return redirect("/")

    conn=get_conn()
    c=conn.cursor()

    c.execute("SELECT * FROM ponto ORDER BY id DESC")

    dados=c.fetchall()

    conn.close()

    return render_template("relatorio.html",dados=dados)


# -----------------------
# LOGOUT
# -----------------------
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# -----------------------
# RUN
# -----------------------
if __name__=="__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT",5000))
    )