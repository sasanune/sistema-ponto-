from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "chave_secreta_simples"

ADMIN_SENHA = "1234"

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
            horas REAL
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
# Login
# -----------------------
@app.route("/", methods=["GET", "POST"])
def login():

    # 🔥 limpa sessão sempre que abrir login
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

        # ADMIN
        if senha_admin:
            if senha_admin == ADMIN_SENHA:
                session["usuario"] = "ADMIN"
                conn.close()
                return redirect("/relatorio")
            else:
                erro = "Senha inválida"

        # FUNCIONÁRIO
        elif usuario:
            session["usuario"] = usuario
            conn.close()
            return redirect("/home")

    conn.close()
    return render_template("login.html", usuarios=usuarios, erro=erro)
# -----------------------
# Página principal (FUNCIONÁRIO)
# -----------------------
@app.route("/home")
def home():
    if "usuario" not in session:
        return redirect("/")

    if session["usuario"] == "ADMIN":
        return redirect("/relatorio")

    usuario = session["usuario"]
    data = datetime.now().strftime("%d/%m/%Y")

    conn = sqlite3.connect("banco.db")
    c = conn.cursor()

    c.execute("""
        SELECT data, entrada, saida_almoco, volta_almoco, saida_final, horas
        FROM ponto
        WHERE funcionario = ?
        ORDER BY id DESC
    """, (usuario,))
    dados = c.fetchall()

    c.execute("""
        SELECT ROUND(SUM(horas), 2)
        FROM ponto
        WHERE funcionario = ?
    """, (usuario,))
    total = c.fetchone()[0] or 0

    # 🔽 pegar último registro do dia
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
        proxima=proxima
    )
@app.route("/bater", methods=["POST"])
def bater():
    if session.get("usuario") in (None, "ADMIN"):
        return redirect("/")

    usuario = session["usuario"]
    data = request.form["data"]
    agora = datetime.now().strftime("%H:%M")

    conn = sqlite3.connect("banco.db")
    c = conn.cursor()

    c.execute("""
        SELECT id, entrada, saida_almoco, volta_almoco, saida_final
        FROM ponto
        WHERE funcionario=? AND data=?
        ORDER BY id DESC LIMIT 1
    """, (usuario, data))

    row = c.fetchone()

    # -------------------------
    # NÃO EXISTE REGISTRO → ENTRADA
    # -------------------------
    if not row:
        c.execute("""
            INSERT INTO ponto 
            VALUES (NULL, ?, ?, ?, NULL, NULL, NULL, NULL)
        """, (usuario, data, agora))

    else:
        pid, e, sa, va, sf = row

        # evita batida dupla no mesmo minuto
        ultimo = sf or va or sa or e
        if ultimo == agora:
            conn.close()
            return redirect("/home")

        if e and not sa:
            c.execute("UPDATE ponto SET saida_almoco=? WHERE id=?", (agora, pid))

        elif sa and not va:
            c.execute("UPDATE ponto SET volta_almoco=? WHERE id=?", (agora, pid))

        elif va and not sf:
            formato = "%H:%M"

            def em_minutos(h):
                t = datetime.strptime(h, formato)
                return t.hour * 60 + t.minute

            total_min = (em_minutos(sa) - em_minutos(e)) + (em_minutos(agora) - em_minutos(va))
            horas = round(total_min / 60, 2)

            c.execute("""
                UPDATE ponto 
                SET saida_final=?, horas=? 
                WHERE id=?
            """, (agora, horas, pid))

        else:
            # já fechou → cria novo ciclo no mesmo dia
            c.execute("""
                INSERT INTO ponto 
                VALUES (NULL, ?, ?, ?, NULL, NULL, NULL, NULL)
            """, (usuario, data, agora))

    conn.commit()
    conn.close()

    return redirect("/home")
# -----------------------
# Relatório (ADMIN)
# -----------------------
@app.route("/relatorio")
def relatorio():
    if session.get("usuario") != "ADMIN":
        return redirect("/")

    conn = sqlite3.connect("banco.db")
    c = conn.cursor()

    c.execute("""
    SELECT 
        id,
        funcionario,
        data,
        entrada,
        saida_almoco,
        volta_almoco,
        saida_final,
        horas
    FROM ponto
    ORDER BY data DESC, id DESC
    """)

    dados = c.fetchall()
    conn.close()

    return render_template("relatorio.html", dados=dados)

# -----------------------
# Zerar horas (ADMIN)
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
# Editar Ponto
# -----------------------
@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editar(id):
    if "usuario" not in session or session["usuario"] != "ADMIN":
        return redirect("/")

    conn = sqlite3.connect("banco.db")
    c = conn.cursor()

    if request.method == "POST":
        entrada = request.form["entrada"]
        saida_almoco = request.form["saida_almoco"]
        volta_almoco = request.form["volta_almoco"]
        saida_final = request.form["saida_final"]

        horas = None

        # recalcular horas
        if entrada and saida_almoco and volta_almoco and saida_final:
            formato = "%H:%M"

            def em_minutos(h):
                t = datetime.strptime(h, formato)
                return t.hour * 60 + t.minute

            total_min = (
                em_minutos(saida_almoco) - em_minutos(entrada)
            ) + (
                em_minutos(saida_final) - em_minutos(volta_almoco)
            )

            horas = round(total_min / 60, 2)

        c.execute("""
            UPDATE ponto
            SET entrada=?,
                saida_almoco=?,
                volta_almoco=?,
                saida_final=?,
                horas=?
            WHERE id=?
        """, (entrada, saida_almoco, volta_almoco, saida_final, horas, id))

        conn.commit()
        conn.close()
        return redirect("/relatorio")

    c.execute("SELECT * FROM ponto WHERE id=?", (id,))
    registro = c.fetchone()
    conn.close()

    return render_template("editar.html", registro=registro)
# -----------------------
# Logout
# -----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

#  IMPORTANTE PARA O RENDER
import os

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
