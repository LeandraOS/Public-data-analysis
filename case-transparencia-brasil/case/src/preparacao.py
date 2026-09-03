"""
preparacao.py — Camada de TRATAMENTO (silver) e modelagem (Etapa 3).

Cada função corresponde a uma decisão metodológica única e reversível.
`preparar()` apenas as encadeia, registrando quantas linhas entram e saem de
cada passo. Esse log é o que permite reconciliar 2.706 linhas brutas com o
n final de qualquer tabela do relatório — requisito de auditabilidade que,
na prática, é o que distingue uma análise reproduzível de uma repetível.

Regra de ouro adotada: nada é apagado. Registros problemáticos recebem
colunas de marcação (`flag_*`) e um campo `escopo_preco` que define sua
elegibilidade para a análise de preços. As exclusões acontecem no ponto de
uso, por filtro explícito e documentado, não na base.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import config, qualidade as q

log = logging.getLogger(__name__)


def tipar(df: pd.DataFrame) -> pd.DataFrame:
    """Converte cada coluna para seu tipo lógico e padroniza ausências."""
    out = q.marcar_nulos(df)

    for c in config.COLUNAS_NUMERICAS_BR:
        out[c] = q.para_numero_br(df[c])

    for c in config.COLUNAS_DATA:
        # utc=True: a fonte grava offset 'Z'. Manter tudo em UTC evita
        # comparações entre instantes com fusos distintos. A conversão para
        # horário local só é feita na apresentação, se necessária.
        out[c] = pd.to_datetime(df[c], utc=True, errors="coerce")

    # Identificadores permanecem como texto: são rótulos, não grandezas.
    # Somar ou tirar média de um CNPJ não significa nada, e a conversão
    # numérica destruiria zeros à esquerda.
    for c, t in config.SCHEMA_ESPERADO.items():
        if t == "id" and c in out:
            out[c] = out[c].astype("string")

    # codigoMunicipio vem corrompido por formatação de planilha
    # ('4.108.403,00'). Reconstituímos o código IBGE de 7 dígitos a partir
    # da parte inteira.
    cod = q.para_numero_br(df["codigoMunicipio"])
    out["codigoMunicipio"] = (
        cod.astype("Float64").round(0).astype("Int64").astype("string").str.zfill(7)
    )
    out.loc[cod.isna(), "codigoMunicipio"] = pd.NA

    for c in ["modalidade", "criterioJulgamento", "forma", "estado", "poder", "esfera",
              "nomeUnidadeFornecimento", "siglaUnidadeFornecimento"]:
        out[c] = out[c].astype("string")

    return out


def descartar_colunas_vazias(df: pd.DataFrame) -> pd.DataFrame:
    """Remove colunas sem qualquer conteúdo informativo.

    Critério: 100% ausente, ou constante em toda a base (variância zero).
    Uma coluna constante não carrega informação para nenhuma análise
    condicional — o conteúdo dela migra para a documentação, não para a tabela.
    """
    descartar = []
    for c in df.columns:
        s = df[c]
        if s.isna().all():
            descartar.append((c, "100% ausente"))
        elif s.nunique(dropna=True) <= 1 and c not in ("codigoClasse", "nomeClasse"):
            descartar.append((c, "constante"))
    # codigoClasse/nomeClasse são constantes (6505 / DROGAS E MEDICAMENTOS):
    # descartamos das colunas e preservamos como metadado do recorte.
    for c in ("codigoClasse", "nomeClasse"):
        if c in df.columns and df[c].nunique(dropna=True) <= 1:
            descartar.append((c, "constante — recorte da extração"))

    for c, motivo in descartar:
        log.info("Coluna descartada: %s (%s)", c, motivo)
    return df.drop(columns=[c for c, _ in descartar]), descartar


def deduplicar(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Resolve duplicidade na chave de negócio (idCompra, numeroItemCompra).

    A base tem duas chaves candidatas com semânticas diferentes:
      - `idItemCompra`: chave técnica, única (2.706 valores para 2.706 linhas);
      - `(idCompra, numeroItemCompra)`: chave de NEGÓCIO — o item n da compra X.

    Três pares violam a segunda: o mesmo item da mesma compra aparece duas
    vezes, com `idItemCompra` diferentes, fornecedores diferentes e
    `dataHoraAtualizacaoItem` diferentes. A interpretação mais parcimoniosa é
    que a extração capturou duas *versões* do mesmo item ao longo do tempo —
    o registro foi retificado na origem (troca de fornecedor, correção de
    quantidade) e a coleta preservou ambas.

    Decisão: manter a versão mais recente por `dataHoraAtualizacaoItem`
    (dimensão de mudança lenta tipo 1, na terminologia de Kimball). Contar as
    duas versões inflaria artificialmente valor e contagem de itens.
    As versões descartadas são devolvidas para inspeção, não apagadas.
    """
    chave = ["idCompra", "numeroItemCompra"]
    ordenado = df.sort_values("dataHoraAtualizacaoItem", ascending=False, kind="mergesort")
    manter = ~ordenado.duplicated(chave, keep="first")
    return ordenado[manter].sort_index(), ordenado[~manter].sort_index()


def normalizar_entidades(df: pd.DataFrame) -> pd.DataFrame:
    """Resolve identidade de fornecedores e cria chaves canônicas.

    Problema: 526 CNPJs distintos convivem com 560 razões sociais — 48 CNPJs
    aparecem com mais de uma grafia ('ASLI COMERCIAL EIRELI' vs
    'ASLI COMERCIAL LTDA', efeito da migração EIRELI→LTDA da Lei 14.195/2021).
    Contar fornecedores por nome superestimaria o número de participantes e
    subestimaria a concentração de mercado.

    Decisão: o CNPJ é a identidade. Adotamos como nome canônico a grafia
    associada ao registro mais recente daquele CNPJ (regra determinística e
    reproduzível, preferível a escolher a mais frequente — que empata — ou a
    mais longa — que é arbitrária).

    Adicionalmente criamos `raizCnpj` (8 primeiros dígitos): identifica o
    grupo econômico, agregando matriz e filiais. Análises de concentração
    devem usar a raiz; análises de contratação, o CNPJ completo.
    """
    out = df.copy()
    out["raizCnpj"] = out["niFornecedor"].str.replace(r"\D", "", regex=True).str.zfill(14).str[:8]
    out["cnpjValido"] = out["niFornecedor"].map(q.cnpj_valido)

    canonico = (
        out.sort_values("dataHoraAtualizacaoItem")
        .groupby("niFornecedor")["nomeFornecedor"]
        .last()
    )
    out["fornecedorCanonico"] = out["niFornecedor"].map(canonico)
    out["fornecedorNormalizado"] = q.normalizar_texto(out["fornecedorCanonico"])
    out["uasgNormalizada"] = q.normalizar_texto(out["nomeUasg"])
    out["marcaNormalizada"] = q.normalizar_texto(out["marca"])
    out["marcaInformativa"] = ~q.marca_nao_informativa(out["marca"])
    return out


def criar_variaveis(df: pd.DataFrame) -> pd.DataFrame:
    """Deriva as variáveis analíticas.

    Nota importante sobre `valorTotalItem = quantidade * precoUnitario`:
    é uma reconstrução, não um campo da fonte. Ela é o valor *homologado* do
    item, que não equivale a valor efetivamente pago — em compras via SISRP
    (registro de preços), a ata registra o preço e a quantidade máxima, e o
    empenho posterior pode ser parcial. Toda leitura financeira desta base é,
    portanto, uma leitura de valor contratado/registrado, e é assim que os
    resultados são reportados.
    """
    out = df.copy()
    out["valorTotalItem"] = out["quantidade"] * out["precoUnitario"]
    out["logPrecoUnitario"] = np.log(out["precoUnitario"].where(out["precoUnitario"] > 0))
    out["logQuantidade"] = np.log(out["quantidade"].where(out["quantidade"] > 0))

    out["anoCompra"] = out["dataCompra"].dt.year
    _naive = out["dataCompra"].dt.tz_localize(None)  # to_period não opera em série com fuso
    out["mesCompra"] = _naive.dt.to_period("M").astype("string")
    out["trimestreCompra"] = _naive.dt.to_period("Q").astype("string")

    out["diasAteAtualizacao"] = (out["dataHoraAtualizacaoItem"] - out["dataCompra"]).dt.days
    out["itensNaCompra"] = out.groupby("idCompra")["idItemCompra"].transform("size")

    # Rótulos legíveis, mantendo os códigos originais ao lado
    out["formaDesc"] = out["forma"].map(config.DOM_FORMA)
    out["modalidadeDesc"] = out["modalidade"].map(config.DOM_MODALIDADE)
    out["criterioDesc"] = out["criterioJulgamento"].fillna("").map(config.DOM_CRITERIO)
    out["esferaDesc"] = out["esfera"].map(config.DOM_ESFERA).fillna("Não informado")
    out["poderDesc"] = out["poder"].map(config.DOM_PODER).fillna("Não informado")

    out["ehConsorcio"] = out["uasgNormalizada"].str.contains("CONSORCIO", na=False)
    return out


def marcar_e_definir_escopo(df: pd.DataFrame, df_bruto_alinhado: pd.DataFrame) -> pd.DataFrame:
    """Anexa marcações de qualidade e classifica cada linha em um escopo de uso.

    `escopo_preco` responde a uma única pergunta: este registro pode entrar
    numa estatística de preço unitário?

      - 'comparavel'          : sim.
      - 'unidade_divergente'  : não — a unidade de fornecimento não é
                                comparável a comprimido/cápsula, ou é ausente.
      - 'preco_implausivel'   : não — preço a mais de 3,5 escores-z modificados
                                da mediana do item, e/ou assinatura de valor
                                de lote lançado como preço unitário.
      - 'criterio_desconto'   : não — nos registros com critério 'maior
                                desconto', `precoUnitario` conflita com
                                `percentualMaiorDesconto` (o preço parece ser
                                o de referência, não o final). Semântica
                                distinta ⇒ não comparável.

    Registros fora de escopo continuam na base e são usados nas análises
    que não dependem de preço (contagem, cobertura territorial, concentração).
    """
    out = df.copy()
    _, marcacoes = q.avaliar(df_bruto_alinhado)
    marcacoes = marcacoes.reindex(out.index)
    for col in marcacoes.columns:
        out[f"flag_{col}"] = marcacoes[col]

    unidade_ruim = ~q.escopo_comparavel(df_bruto_alinhado).reindex(out.index).fillna(False)
    preco_ruim = (marcacoes.get("ACUR-01", False) | marcacoes.get("ACUR-02", False))
    desconto = out["criterioJulgamento"].eq("D").fillna(False)

    escopo = pd.Series("comparavel", index=out.index, dtype="object")
    escopo[desconto] = "criterio_desconto"
    escopo[preco_ruim.fillna(False)] = "preco_implausivel"
    escopo[unidade_ruim] = "unidade_divergente"
    out["escopo_preco"] = escopo
    return out


def preparar(df_bruto: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Pipeline completo de tratamento, com log de linhagem."""
    linhagem = [("bruto", len(df_bruto), "leitura do CSV")]

    df = tipar(df_bruto)
    linhagem.append(("tipado", len(df), "tipos aplicados, sentinelas 'NA' -> nulo"))

    df, descartadas = descartar_colunas_vazias(df)
    linhagem.append(("colunas_descartadas", len(df), f"{len(descartadas)} colunas sem informação"))

    df, versoes_antigas = deduplicar(df)
    linhagem.append(("deduplicado", len(df), f"{len(versoes_antigas)} versões antigas removidas"))

    df = normalizar_entidades(df)
    df = criar_variaveis(df)
    df = marcar_e_definir_escopo(df, df_bruto.loc[df.index])
    linhagem.append(("final", len(df), "variáveis derivadas e escopo definido"))

    meta = {
        "linhagem": pd.DataFrame(linhagem, columns=["etapa", "n_linhas", "observacao"]),
        "colunas_descartadas": pd.DataFrame(descartadas, columns=["coluna", "motivo"]),
        "versoes_antigas": versoes_antigas,
        "distribuicao_escopo": df["escopo_preco"].value_counts(),
    }
    return df, meta


def base_precos(df: pd.DataFrame) -> pd.DataFrame:
    """Subconjunto elegível para estatísticas de preço unitário."""
    return df[df["escopo_preco"].eq("comparavel")].copy()
