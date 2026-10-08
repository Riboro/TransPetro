import os, hmac, hashlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Base, engine, SessionLocal, get_db
from models import Usuario, Topico, Questao, RespostaUsuario

NIVEIS = {1: "Não sabe", 2: "Chutômetro", 3: "Sabe responder", 4: "Domina a questão"}
LETRAS = "ABCDE"


# ---------- senha (PBKDF2 da stdlib) ----------
def hash_pw(senha: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${h}"


def check_pw(senha: str, guardado: str) -> bool:
    return hmac.compare_digest(hash_pw(senha, guardado.split("$")[0]), guardado)


# ---------- app ----------
def seed():
    with SessionLocal() as db:
        # Só popula um banco REALMENTE novo. Antes, bastava não haver tópicos (por exemplo, depois de
        # você excluí-los) para os exemplos serem recriados a cada deploy/reinício.
        if db.query(Usuario).count() or db.query(Topico).count():
            return
        t1, t2 = Topico(nome="Direito Constitucional"), Topico(nome="Português")
        db.add_all([t1, t2]); db.flush()
        db.add_all([
            Questao(topico_id=t1.id, enunciado="Segundo a CF/88, a República Federativa do Brasil tem como fundamento:",
                    opcao_a="A soberania", opcao_b="A erradicação da pobreza", opcao_c="A redução das desigualdades regionais",
                    opcao_d="A construção de uma sociedade livre, justa e solidária", opcao_e="A garantia do desenvolvimento nacional",
                    resposta_correta="A"),
            Questao(topico_id=t2.id, enunciado="Assinale a frase em que o uso da crase está correto:",
                    opcao_a="Fui à pé até a escola.", opcao_b="Entreguei o livro à ela.", opcao_c="Refiro-me à situação descrita.",
                    opcao_d="Começou a chover à partir das 10h.", opcao_e="Ela chegou à tempo.", resposta_correta="C"),
        ])
        db.commit()


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    seed()
    yield


app = FastAPI(title="Estudos para Concursos", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-troque-em-producao"),
                   max_age=60 * 60 * 24 * 14, https_only=bool(os.getenv("RENDER")))
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def go(url: str):
    return RedirectResponse(url, status_code=303)


def usuario_atual(request: Request, db: Session):
    uid = request.session.get("uid")
    return db.get(Usuario, uid) if uid else None


def render(request, nome, ctx=None, status=200):
    return templates.TemplateResponse(request, nome, ctx or {}, status_code=status)


# ---------- autenticação ----------
@app.get("/")
def home(request: Request):
    return go("/dashboard" if request.session.get("uid") else "/login")


@app.get("/login")
def login_form(request: Request):
    return render(request, "login.html", {"modo": "login"})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    u = db.query(Usuario).filter_by(username=username.strip()).first()
    if not u or not check_pw(password, u.password):
        return render(request, "login.html", {"modo": "login", "erro": "Usuário ou senha incorretos."}, 400)
    request.session["uid"] = u.id
    return go("/dashboard")


@app.get("/registro")
def registro_form(request: Request):
    return render(request, "login.html", {"modo": "registro"})


@app.post("/registro")
def registro(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    username = username.strip()
    erro = None
    if len(username) < 3: erro = "O usuário precisa ter ao menos 3 caracteres."
    elif len(password) < 6: erro = "A senha precisa ter ao menos 6 caracteres."
    elif db.query(Usuario).filter_by(username=username).first(): erro = "Esse usuário já existe."
    if erro:
        return render(request, "login.html", {"modo": "registro", "erro": erro}, 400)
    u = Usuario(username=username, password=hash_pw(password))
    db.add(u); db.commit()
    request.session["uid"] = u.id
    return go("/dashboard")


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return go("/login")


# ---------- dashboard ----------
@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    u = usuario_atual(request, db)
    if not u: return go("/login")
    resp = db.query(RespostaUsuario).filter_by(usuario_id=u.id).all()
    total, acertos = len(resp), sum(r.acertou for r in resp)
    por_nivel = []
    for n, nome in NIVEIS.items():
        rs = [r for r in resp if r.nivel_confianca == n]
        a = sum(r.acertou for r in rs)
        por_nivel.append({"nivel": n, "nome": nome, "total": len(rs), "taxa": round(100 * a / len(rs)) if rs else 0})
    return render(request, "dashboard.html", {
        "user": u, "total": total, "acertos": acertos,
        "pct": round(100 * acertos / total) if total else 0,
        "por_nivel": por_nivel, "topicos": db.query(Topico).order_by(Topico.nome).all()})


# ---------- tópicos (criar / excluir) ----------
def pagina_topicos(request, db, u, erro=None, status=200):
    return render(request, "topicos.html", {"user": u, "erro": erro,
                  "topicos": db.query(Topico).order_by(Topico.nome).all()}, status)


@app.get("/topicos")
def topicos(request: Request, db: Session = Depends(get_db)):
    u = usuario_atual(request, db)
    if not u: return go("/login")
    return pagina_topicos(request, db, u)


@app.post("/topicos")
def criar_topico(request: Request, nome: str = Form(""), db: Session = Depends(get_db)):
    u = usuario_atual(request, db)
    if not u: return go("/login")
    nome = nome.strip()
    if not nome:
        return pagina_topicos(request, db, u, "Digite o nome do tópico.", 400)
    if db.query(Topico).filter(func.lower(Topico.nome) == nome.lower()).first():
        return pagina_topicos(request, db, u, "Já existe um tópico com esse nome.", 400)
    db.add(Topico(nome=nome)); db.commit()
    return go("/topicos")


@app.post("/topicos/{tid}/excluir")
def excluir_topico(tid: int, request: Request, db: Session = Depends(get_db)):
    u = usuario_atual(request, db)
    if not u: return go("/login")
    t = db.get(Topico, tid)
    if t:
        db.delete(t); db.commit()  # apaga também as questões e respostas do tópico
    return go("/topicos")


# ---------- questões ----------
def ultima_resposta(db, uid, qid):
    return (db.query(RespostaUsuario).filter_by(usuario_id=uid, questao_id=qid)
            .order_by(RespostaUsuario.id.desc()).first())


@app.get("/questoes")
def lista(request: Request, topico_id: int | None = None, db: Session = Depends(get_db)):
    u = usuario_atual(request, db)
    if not u: return go("/login")
    q = db.query(Questao)
    if topico_id: q = q.filter(Questao.topico_id == topico_id)
    ult = {}
    for r in db.query(RespostaUsuario).filter_by(usuario_id=u.id).order_by(RespostaUsuario.id):
        ult[r.questao_id] = r
    return render(request, "questoes.html", {
        "user": u, "questoes": q.order_by(Questao.id).all(), "ult": ult, "niveis_txt": NIVEIS,
        "topicos": db.query(Topico).order_by(Topico.nome).all(), "topico_id": topico_id})


def pagina_form_questao(request, db, u, v=None, erro=None, status=200):
    return render(request, "questao_form.html", {
        "user": u, "v": v or {}, "erro": erro, "letras": LETRAS,
        "topicos": db.query(Topico).order_by(Topico.nome).all()}, status)


# /questoes/nova precisa vir ANTES de /questoes/{qid}
@app.get("/questoes/nova")
def nova_questao_form(request: Request, topico_id: int | None = None, db: Session = Depends(get_db)):
    u = usuario_atual(request, db)
    if not u: return go("/login")
    return pagina_form_questao(request, db, u, {"topico_id": topico_id})


@app.post("/questoes/nova")
def nova_questao(request: Request, topico_id: int = Form(0), enunciado: str = Form(""),
                 opcao_a: str = Form(""), opcao_b: str = Form(""), opcao_c: str = Form(""),
                 opcao_d: str = Form(""), opcao_e: str = Form(""), resposta_correta: str = Form(""),
                 db: Session = Depends(get_db)):
    u = usuario_atual(request, db)
    if not u: return go("/login")
    v = {"topico_id": topico_id, "enunciado": enunciado.strip(), "opcao_a": opcao_a.strip(),
         "opcao_b": opcao_b.strip(), "opcao_c": opcao_c.strip(), "opcao_d": opcao_d.strip(),
         "opcao_e": opcao_e.strip(), "resposta_correta": resposta_correta.strip().upper()}
    erro = None
    if not db.get(Topico, topico_id): erro = "Escolha um tópico."
    elif not v["enunciado"]: erro = "Escreva o enunciado."
    elif not all(v[f"opcao_{l.lower()}"] for l in LETRAS): erro = "Preencha as cinco alternativas."
    elif v["resposta_correta"] not in LETRAS: erro = "Marque qual alternativa é a correta."
    if erro:
        return pagina_form_questao(request, db, u, v, erro, 400)
    db.add(Questao(**v)); db.commit()
    return go(f"/questoes?topico_id={topico_id}")


@app.get("/questoes/{qid}")
def ver_questao(qid: int, request: Request, db: Session = Depends(get_db)):
    u = usuario_atual(request, db)
    if not u: return go("/login")
    q = db.get(Questao, qid)
    if not q: raise HTTPException(404, "Questão não encontrada")
    ult = ultima_resposta(db, u.id, qid)
    # próxima questão NÃO respondida do mesmo tema (depois desta; se não houver, volta ao início)
    respondidas = {x for (x,) in db.query(RespostaUsuario.questao_id).filter_by(usuario_id=u.id)}
    pend = [x for (x,) in db.query(Questao.id).filter(Questao.topico_id == q.topico_id, Questao.id != qid)
            .order_by(Questao.id) if x not in respondidas]
    prox = next((x for x in pend if x > qid), pend[0] if pend else None)
    return render(request, "questao.html", {
        "user": u, "q": q, "niveis": NIVEIS, "prox": prox,
        "opcoes": [(l, getattr(q, f"opcao_{l.lower()}")) for l in LETRAS],
        "ult": ult, "mostrar": ult is not None and request.query_params.get("respondida") == "1"})


@app.post("/questoes/{qid}/responder")
def responder(qid: int, request: Request, alternativa: str = Form(...), nivel_confianca: int = Form(...),
              db: Session = Depends(get_db)):
    u = usuario_atual(request, db)
    if not u: return go("/login")
    q = db.get(Questao, qid)
    if not q: raise HTTPException(404, "Questão não encontrada")
    alternativa = alternativa.strip().upper()
    if alternativa not in LETRAS:
        raise HTTPException(400, "Alternativa inválida (use A–E).")
    if nivel_confianca not in NIVEIS:
        raise HTTPException(400, "Nível de confiança inválido (use 1–4).")
    db.add(RespostaUsuario(usuario_id=u.id, questao_id=qid, alternativa_escolhida=alternativa,
                           acertou=(alternativa == q.resposta_correta.upper()), nivel_confianca=nivel_confianca))
    db.commit()
    return go(f"/questoes/{qid}?respondida=1")


@app.post("/questoes/{qid}/excluir")
def excluir_questao(qid: int, request: Request, db: Session = Depends(get_db)):
    u = usuario_atual(request, db)
    if not u: return go("/login")
    q = db.get(Questao, qid)
    tid = q.topico_id if q else None
    if q:
        db.delete(q); db.commit()
    return go(f"/questoes?topico_id={tid}" if tid else "/questoes")
