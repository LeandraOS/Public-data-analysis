"""
ingestao.py — Camada de LEITURA (bronze).

Responsabilidade única: trazer o arquivo bruto para memória preservando
fidelidade ao original, e validar o contrato de schema.

Princípio adotado: nesta camada NADA é convertido, corrigido ou descartado.
Todas as colunas são lidas como texto. Isso separa de forma auditável o que
veio da fonte do que foi decidido pelo analista — se a conversão de tipo
acontecesse aqui, um erro de parsing seria indistinguível de um dado ausente
na origem (arquitetura bronze/silver/gold; cf. DAMA-DMBOK, cap. 13).
"""

from __future__ import annotations

import hashlib
import logging

import pandas as pd

from . import config

log = logging.getLogger(__name__)


class ErroContratoSchema(Exception):
    """Levantada quando a estrutura do arquivo divergir do contrato."""


def hash_arquivo(caminho) -> str:
    """SHA-256 do arquivo bruto.

    Registrar o hash da entrada é o que torna um resultado *reproduzível* e
    não apenas *repetível*: permite provar que duas execuções partiram
    exatamente do mesmo insumo.
    """
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def validar_schema(df: pd.DataFrame, estrito: bool = False) -> dict:
    """Compara as colunas lidas com o contrato declarado em config.

    Retorna um relatório em vez de apenas falhar, porque em coleta recorrente
    o mais comum não é o arquivo estar 'errado', e sim a API ter evoluído.
    O relatório é o insumo do alerta operacional.
    """
    esperadas = set(config.SCHEMA_ESPERADO)
    lidas = set(df.columns)

    relatorio = {
        "n_linhas": len(df),
        "n_colunas": df.shape[1],
        "colunas_ausentes": sorted(esperadas - lidas),
        "colunas_novas": sorted(lidas - esperadas),
        "ordem_alterada": list(df.columns) != list(config.SCHEMA_ESPERADO),
    }

    if estrito and (relatorio["colunas_ausentes"] or relatorio["colunas_novas"]):
        raise ErroContratoSchema(relatorio)

    if relatorio["colunas_ausentes"]:
        log.warning("Colunas ausentes: %s", relatorio["colunas_ausentes"])
    if relatorio["colunas_novas"]:
        log.warning("Colunas novas (não previstas): %s", relatorio["colunas_novas"])

    return relatorio


def ler_bruto(caminho=None) -> tuple[pd.DataFrame, dict]:
    """Lê o CSV bruto integralmente como texto.

    `dtype=str` + `keep_default_na=False` são deliberados:

    - `dtype=str` impede que o pandas infira tipos. Sem isso, `codigoMunicipio`
      ("4.108.403,00") viria como texto por acidente e `modalidade` viria como
      inteiro, quebrando joins com tabelas de domínio; e um CNPJ com zero à
      esquerda perderia o zero.
    - `keep_default_na=False` impede que a string literal "NA" — que nesta
      base é o sentinela de ausência gravado pela API — seja convertida em
      NaN antes de ser contabilizada. Queremos medir explicitamente quantos
      "NA" existem, e distinguir "NA" (ausência declarada pela fonte) de
      célula vazia (ausência estrutural do arquivo).
    """
    caminho = caminho or config.ARQUIVO_BRUTO
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False, encoding="utf-8")
    df.columns = [c.strip() for c in df.columns]

    meta = {
        "arquivo": str(caminho),
        "sha256": hash_arquivo(caminho),
        "schema": validar_schema(df),
    }
    log.info("Lidas %d linhas x %d colunas", *df.shape)
    return df, meta
