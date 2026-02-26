from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
import os

app = Flask(__name__)
app.secret_key = "chave_secreta_simples"

ADMIN_SENHA = "1234"

# timezone Brasília
BRASILIA = ZoneInfo("America/Sao_Paulo")


# -----------------------
# Criar banco
# -----------------------
def criar_banco():

    conn = sqlite3.connect("banco.db")
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

    # garante que a coluna existe (para bancos antigos)
    try:
        c.execute("ALTER TABLE ponto ADD COLUMN horas_extras REAL DEFAULT 0")
    except:
        pass

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
# Login
# -----------------------
@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        session.clear()

    conn = sqlite3.connect("banco.db")
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

    conn = sqlite3.connect("banco.db")
    c = conn.cursor()

    c.execute("""
        SELECT data, entrada, saida_almoco, volta_almoco, saida_final, horas, horas_extras
        FROM ponto
        WHERE funcionario=?
        ORDER BY id DESC
    """, (usuario,))

    dados = c.fetchall()

    c.execute("""
        SELECT ROUND(SUM(horas),2),
               ROUND(SUM(horas_extras),2)
        FROM ponto
        WHERE funcionario=?
    """, (usuario,))

    row_total = c.fetchone()

    total = row_total[0] or 0
    total_extra = row_total[1] or 0

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
        total=total,
        total_extra=total_extra,
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

    agora_dt = datetime.now(BRASILIA)

    agora = agora_dt.strftime("%H:%M")
    data = agora_dt.strftime("%d/%m/%Y")

    conn = sqlite3.connect("banco.db")
    c = conn.cursor()

    c.execute("""
        SELECT id, entrada, saida_almoco, volta_almoco, saida_final
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

        ultimo = sf or va or sa or e

        if ultimo == agora:
            conn.close()
            return redirect("/home")

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

            formato = "%H:%M"

            def em_min(h):
                t = datetime.strptime(h, formato)
                return t.hour*60+t.minute

            total_min = (
                em_min(sa) - em_min(e)
            ) + (
                em_min(agora) - em_min(va)
            )

            horas = round(total_min/60, 2)

            if horas > 9:
                horas_extras = round(horas - 9, 2)
            else:
                horas_extras = 0

            c.execute("""
                UPDATE ponto
                SET saida_final=?,
                    horas=?,
                    horas_extras=?
                WHERE id=?
            """, (agora, horas, horas_extras, pid))

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

    conn = sqlite3.connect("banco.db")
    c = conn.cursor()

    c.execute("""
        SELECT *
        FROM ponto
        ORDER BY id DESC
    """)

    dados = c.fetchall()

    conn.close()

    return render_template(
        "relatorio.html",
        dados=dados
    )


# -----------------------
# ZERAR
# -----------------------
@app.route("/zerar-horas", methods=["POST"])
def zerar_horas():

    if session.get("usuario") != "ADMIN":
        return redirect("/")

    conn = sqlite3.connect("banco.db")
    c = conn.cursor()

    c.execute("DELETE FROM ponto")

    conn.commit()
    conn.close()

    return redirect("/relatorio")


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
        port=int(os.environ.get("PORT", 5000)),
        debug=True
    )