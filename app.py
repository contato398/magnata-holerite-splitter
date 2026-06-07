import os
import re
import io
import zipfile
import base64
from flask import Flask, request, jsonify
import pdfplumber
from pypdf import PdfReader, PdfWriter

app = Flask(__name__)

def extrair_cpf(texto):
    if not texto:
        return None
    linhas = texto.split('\n')
    for i, linha in enumerate(linhas):
        if 'CPF' in linha:
            cpf_match = re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', linha)
            if cpf_match:
                return cpf_match.group()
            if i + 1 < len(linhas):
                cpf_match = re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', linhas[i + 1])
                if cpf_match:
                    return cpf_match.group()
    cpf_match = re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', texto)
    if cpf_match:
        return cpf_match.group()
    return None

def extrair_nome_funcionario(texto):
    if not texto:
        return "Desconhecido"
    linhas = texto.split('\n')
    for i, linha in enumerate(linhas):
        if 'Nome do Funcionário' in linha or 'Nome do Funcionario' in linha:
            if i + 1 < len(linhas):
                proxima = linhas[i + 1].strip()
                partes = proxima.split()
                if partes and partes[0].isdigit():
                    nome_partes = []
                    for p in partes[1:]:
                        if re.match(r'^\d{5,6}$', p):
                            break
                        nome_partes.append(p)
                    if nome_partes:
                        return ' '.join(nome_partes)
    return "Desconhecido"

def separar_pdf_por
