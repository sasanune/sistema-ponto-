from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
import os

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.abspath(".")

app = Flask(
    __name__,
    template_folder=os.path.join(base_path, "templates"),
    static_folder=os.path.join(base_path, "static")
)
app.secret_key = "chave_secreta_simples"

ADMIN_SENHA = "1234"

BRASILIA = ZoneInfo("America/Sao_Paulo")


# -----------------------
# CONEXÃO BANCO
# -----------------------
def conectar():

    if getattr(sys, 'frozen', False):
        pasta = os.path.dirname(sys.executable)
    else:
        pasta = os.path.abspath(".")

    caminho = os.path.join(pasta, "banco.db")

    return sqlite3.connect(caminho)

# -----------------------
# CRIAR BANCO
# -----------------------
def criar_banco():

    conn = conectar()
    c = conn.cursor()

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
            horas_extras REAL DEFAULT 0
        )
    """)

    c.execute("SELECT COUNT(*) FROM usuarios")

    if c.fetchone()[0] == 0:

        c.executemany(
            "INSERT INTO usuarios (nome) VALUES (?)",
            [("João",), ("Maria",), ("Carlos",)]
        )

    conn.commit()
    conn.close()


criar_banco()


# -----------------------
# CALCULAR HORAS
# -----------------------
def calcular_horas(e, sa, va, sf):

    formato = "%H:%M"

    def minutos(h):
        t = datetime.strptime(h, formato)
        return t.hour * 60 + t.minute

    total = (minutos(sa) - minutos(e)) + (minutos(sf) - minutos(va))

    horas = round(total / 60, 2)

    if horas > 8:
        extra = round(horas - 8, 2)
    else:
        extra = 0

    return horas, extra


# -----------------------
# LOGIN
# -----------------------
@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        session.clear()

    conn = conectar()
    c = conn.cursor()

    c.execute("SELECT nome FROM usuarios")
    usuarios = c.fetchall()

    erro = None

    if request.method == "POST":

        senha = request.form.get("admin_senha")
        usuario = request.form.get("usuario")

        if senha:

            if senha == ADMIN_SENHA:

                session["usuario"] = "ADMIN"
                return redirect("/relatorio")

            else:
                erro = "Senha inválida"

        elif usuario:

            session["usuario"] = usuario
            return redirect("/home")

    conn.close()

    return render_template(
        "login.html",
        usuarios=usuarios,
        erro=erro
    )


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

    conn = conectar()
    c = conn.cursor()

    c.execute("""
        SELECT data, entrada, saida_almoco, volta_almoco,
        saida_final, horas, horas_extras
        FROM ponto
        WHERE funcionario=?
        ORDER BY id DESC
    """, (usuario,))

    dados = c.fetchall()

    c.execute("""
        SELECT SUM(horas), SUM(horas_extras)
        FROM ponto
        WHERE funcionario=?
    """, (usuario,))

    total = c.fetchone()

    total_horas = total[0] or 0
    total_extra = total[1] or 0

    c.execute("""
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
        total=round(total_horas,2),
        extra=round(total_extra,2),
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

    conn = conectar()
    c = conn.cursor()

    c.execute("""
        SELECT id, entrada, saida_almoco,
        volta_almoco, saida_final
        FROM ponto
        WHERE funcionario=? AND data=?
        ORDER BY id DESC LIMIT 1
    """, (usuario, data))

    row = c.fetchone()

    if not row:

        c.execute("""
            INSERT INTO ponto
            (funcionario, data, entrada)
            VALUES (?, ?, ?)
        """, (usuario, data, agora))

    else:

        pid, e, sa, va, sf = row

        if e and not sa:

            c.execute(
                "UPDATE ponto SET saida_almoco=? WHERE id=?",
                (agora, pid)
            )

        elif sa and not va:

            c.execute(
                "UPDATE ponto SET volta_almoco=? WHERE id=?",
                (agora, pid)
            )

        elif va and not sf:

            horas, extra = calcular_horas(
                e, sa, va, agora
            )

            c.execute("""
                UPDATE ponto
                SET saida_final=?, horas=?, horas_extras=?
                WHERE id=?
            """, (agora, horas, extra, pid))

        else:

            c.execute("""
                INSERT INTO ponto
                (funcionario, data, entrada)
                VALUES (?, ?, ?)
            """, (usuario, data, agora))

    conn.commit()
    conn.close()

    return redirect("/home")


# -----------------------
# RELATORIO
# -----------------------
@app.route("/relatorio")
def relatorio():

    if session.get("usuario") != "ADMIN":
        return redirect("/")

    conn = conectar()

    dados = conn.execute("""
        SELECT *
        FROM ponto
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "relatorio.html",
        dados=dados
    )


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
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )