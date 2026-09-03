"""
config.py — Parâmetros, caminhos e dicionários de domínio do projeto.

Centralizar constantes em um único módulo é o que permite que decisões
metodológicas sejam auditáveis: qualquer limiar usado na análise aparece
aqui, com justificativa, e não escondido no meio do código.
"""

from pathlib import Path

# --------------------------------------------------------------------------
# Caminhos (relativos à raiz do repositório, para reprodutibilidade)
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_INTERIM = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"
FIGURAS = OUTPUTS / "figuras"

ARQUIVO_BRUTO = DATA_RAW / "compras-gov.csv"

for _d in (DATA_INTERIM, DATA_PROCESSED, OUTPUTS, FIGURAS):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Contrato de schema: colunas esperadas e tipo lógico de cada uma
# --------------------------------------------------------------------------
# "Data contract" no sentido usado por Great Expectations / dbt: a leitura
# falha de forma explícita se o arquivo divergir do esperado, em vez de
# propagar silenciosamente uma mudança de estrutura da API para a análise.
SCHEMA_ESPERADO = {
    "idCompra": "id",
    "idItemCompra": "id",
    "forma": "categoria",
    "modalidade": "categoria",
    "criterioJulgamento": "categoria",
    "numeroItemCompra": "inteiro",
    "descricaoItem": "texto",
    "codigoItemCatalogo": "id",
    "nomeUnidadeMedida": "texto",
    "siglaUnidadeMedida": "categoria",
    "nomeUnidadeFornecimento": "categoria",
    "siglaUnidadeFornecimento": "categoria",
    "capacidadeUnidadeFornecimento": "numero_br",
    "quantidade": "numero_br",
    "precoUnitario": "numero_br",
    "percentualMaiorDesconto": "numero_br",
    "niFornecedor": "id",
    "nomeFornecedor": "texto",
    "marca": "texto",
    "codigoUasg": "id",
    "nomeUasg": "texto",
    "codigoMunicipio": "numero_br",
    "municipio": "texto",
    "estado": "categoria",
    "codigoOrgao": "id",
    "nomeOrgao": "texto",
    "poder": "categoria",
    "esfera": "categoria",
    "dataCompra": "data",
    "dataHoraAtualizacaoCompra": "data",
    "dataHoraAtualizacaoItem": "data",
    "dataResultado": "data",
    "dataHoraAtualizacaoUasg": "data",
    "codigoClasse": "id",
    "nomeClasse": "texto",
}

COLUNAS_NUMERICAS_BR = [c for c, t in SCHEMA_ESPERADO.items() if t == "numero_br"]
COLUNAS_DATA = [c for c, t in SCHEMA_ESPERADO.items() if t == "data"]

# Sentinelas textuais que representam ausência de informação.
# A base tem TRÊS tipos distintos de ausência, todos textuais:
#   1. "NA"  — sentinela gravada pela fonte (milhares de ocorrências);
#   2. " "   — célula com apenas espaço, graficamente idêntica a vazio
#              (74 em criterioJulgamento) — ver qualidade.padding_em_branco;
#   3. "nan" — a string literal 'nan' (9 em codigoMunicipio). Um NaN de
#              Python/pandas serializado como texto: evidência direta de que
#              o arquivo passou por um script ou planilha entre a API e a
#              entrega, e não veio da API diretamente.
# Nenhum deles é reconhecido como nulo pelo pandas com keep_default_na=False,
# e tratá-los é pré-condição para qualquer medida de completude.
SENTINELAS_NULAS = ["NA", "N/A", "", "-", ".", "NULL", "null", "None",
                    "nan", "NaN", "NAN", "SEM MARCA"]

# --------------------------------------------------------------------------
# Dicionários de domínio
# --------------------------------------------------------------------------
# `forma`: documentado no enunciado do case.
DOM_FORMA = {
    "SISPP": "SISPP — Sistema de Preços Praticados",
    "SISRP": "SISRP — Sistema de Registro de Preços",
}

# `modalidade` e `criterioJulgamento`: NÃO documentados no dicionário fornecido
# (o campo criterioJulgamento aparece como "NA"). Os rótulos abaixo são
# HIPÓTESES inferidas por evidência interna — ver docs/02_decisoes_metodologicas.md,
# seção "Decodificação de campos não documentados". Devem ser confirmados
# contra a tabela de domínio da API antes de uso em publicação.
DOM_MODALIDADE = {
    "5": "Pregão (hipótese)",
    "6": "Dispensa de licitação (hipótese)",
}

DOM_CRITERIO = {
    "V": "Menor preço / valor (hipótese)",
    "D": "Maior desconto (hipótese)",
    "1": "Não aplicável — dispensa (hipótese)",
    "": "Não informado",
}

DOM_PODER = {"E": "Executivo", "L": "Legislativo", "J": "Judiciário"}
DOM_ESFERA = {"F": "Federal", "E": "Estadual", "M": "Municipal"}

# Prefixo do código IBGE do município -> UF. Usado como regra de
# consistência referencial entre `codigoMunicipio` e `estado`.
UF_POR_PREFIXO_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP",
    "17": "TO", "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
    "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
    "51": "MT", "52": "GO", "53": "DF",
}

# --------------------------------------------------------------------------
# Parâmetros analíticos (todos os limiares da análise vivem aqui)
# --------------------------------------------------------------------------
# Unidades de fornecimento consideradas comparáveis entre si para
# comparação de preço unitário: formas farmacêuticas sólidas orais, em que
# 1 unidade de fornecimento = 1 dose. Bisnaga/frasco/frasco-ampola medem
# volume ou massa e não são comparáveis a comprimido sem fator de conversão.
UNIDADES_COMPARAVEIS = ["COMPRIMIDO", "CÁPSULA"]

# Limiar do escore-z modificado (Iglewicz & Hoaglin, 1993). O valor 3,5 é
# o recomendado pelos autores; aplicado sobre log(preço) porque a
# distribuição de preços é assimétrica à direita e multiplicativa.
LIMIAR_MZ = 3.5

# Quantidade mínima abaixo da qual o registro é suspeito de conter o valor
# do lote no campo de preço unitário (ver análise de outliers).
QTD_SUSPEITA_LOTE = 1

SEED = 42
