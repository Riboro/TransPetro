from datetime import datetime
from sqlalchemy import (Column, Integer, String, Text, Boolean, DateTime,
                        ForeignKey, CheckConstraint)
from sqlalchemy.orm import relationship
from database import Base


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password = Column(String(256), nullable=False)  # hash PBKDF2 (salt$hash), nunca texto puro


class Topico(Base):
    __tablename__ = "topicos"
    id = Column(Integer, primary_key=True)
    nome = Column(String(120), nullable=False)
    questoes = relationship("Questao", back_populates="topico", cascade="all, delete-orphan")


class Questao(Base):
    __tablename__ = "questoes"
    id = Column(Integer, primary_key=True)
    enunciado = Column(Text, nullable=False)
    opcao_a = Column(Text, nullable=False)
    opcao_b = Column(Text, nullable=False)
    opcao_c = Column(Text, nullable=False)
    opcao_d = Column(Text, nullable=False)
    opcao_e = Column(Text, nullable=False)
    resposta_correta = Column(String(1), nullable=False)
    topico_id = Column(Integer, ForeignKey("topicos.id"), nullable=False, index=True)
    topico = relationship("Topico", back_populates="questoes")
    respostas = relationship("RespostaUsuario", back_populates="questao", cascade="all, delete-orphan")


class RespostaUsuario(Base):
    __tablename__ = "respostas_usuario"
    __table_args__ = (CheckConstraint("nivel_confianca BETWEEN 1 AND 4", name="ck_nivel_confianca"),)
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    questao_id = Column(Integer, ForeignKey("questoes.id"), nullable=False, index=True)
    alternativa_escolhida = Column(String(1), nullable=False)
    acertou = Column(Boolean, nullable=False)
    nivel_confianca = Column(Integer, nullable=False)  # 1 a 4
    respondida_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    questao = relationship("Questao", back_populates="respostas")
