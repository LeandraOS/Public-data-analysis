"""
analise.py — Camada de ANÁLISE (gold) — Etapa 4.

Cada pergunta de pesquisa é uma função pura: recebe a base tratada, devolve
tabelas e figuras. Nenhuma função altera a base. Isso permite reexecutar
qualquer análise isoladamente e torna cada resultado testável.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from . import config

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 130, "font.size": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linestyle": ":",
    "figure.facecolor": "white", "axes.titlesize": 10, "axes.titleweight": "bold",
})
COR = "#1b4965"
COR2 = "#e07a5f"


def _salvar(fig, nome):
    caminho = config.FIGURAS / f"{nome}.png"
    fig.tight_layout()
    fig.savefig(caminho, bbox_inches="tight")
    return caminho


# ==========================================================================
# P1 — Dispersão de preços do mesmo medicamento entre entes compradores
# ==========================================================================


def p1_dispersao_precos(dfp: pd.DataFrame):
    """Quanto varia o preço unitário do MESMO medicamento entre compradores?

    Relevância: medicamentos com o mesmo código CATMAT, mesma dosagem e mesma
    unidade de fornecimento são bens homogêneos. Num mercado competitivo e
    com informação disponível, o preço deveria convergir. Dispersão
    persistente em compras públicas de bens homogêneos é o objeto central da
    literatura de 'desperdício passivo' em compras governamentais (Bandiera,
    Prat & Valletti, 2009): sobrepreço que decorre de gestão e informação
    deficientes, não necessariamente de corrupção. É também a base legal da
    pesquisa de preços (Lei 14.133/2021, art. 23).

    Método: estatísticas robustas por item — mediana, MAD normalizado (MADN),
    razão interdecil P90/P10 e coeficiente de dispersão robusto. Preferimos
    o interdecil ao coeficiente de variação porque este último é definido a
    partir da média e do desvio-padrão, ambos não robustos a caudas longas.
    """
    tab = []
    for (cod, nome), g in dfp.groupby(["codigoItemCatalogo", "descricaoItem"], observed=True):
        p = g["precoUnitario"]
        med = p.median()
        madn = np.median(np.abs(p - med)) / 0.6745  # MADN: comparável a sigma
        tab.append({
            "item": nome, "catmat": cod, "n_itens": len(g),
            "n_compradores": g["codigoUasg"].nunique(),
            "preco_min": p.min(), "P10": p.quantile(0.10), "mediana": med,
            "P90": p.quantile(0.90), "preco_max": p.max(),
            "MADN": madn, "disp_robusta_%": 100 * madn / med,
            "razao_P90_P10": p.quantile(0.90) / p.quantile(0.10),
            "razao_max_min": p.max() / p.min(),
        })
    tabela = pd.DataFrame(tab).sort_values("mediana")

    # Dispersão intra-UF vs entre-UF: decomposição de variância em log
    decomp = []
    for nome, g in dfp.groupby("descricaoItem", observed=True):
        y = g["logPrecoUnitario"].dropna()
        gg = g.loc[y.index]
        media_geral = y.mean()
        entre = (
            gg.groupby("estado", observed=True)["logPrecoUnitario"]
            .agg(["mean", "size"])
            .assign(sq=lambda d: d["size"] * (d["mean"] - media_geral) ** 2)["sq"].sum()
        )
        total = ((y - media_geral) ** 2).sum()
        decomp.append({"item": nome, "var_entre_UF_%": 100 * entre / total,
                       "var_intra_UF_%": 100 * (1 - entre / total)})
    decomposicao = pd.DataFrame(decomp)

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
    for ax, (nome, g) in zip(axes, dfp.groupby("descricaoItem", observed=True)):
        ax.hist(g["precoUnitario"], bins=40, color=COR, alpha=0.85)
        med = g["precoUnitario"].median()
        ax.axvline(med, color=COR2, lw=1.6, label=f"mediana R$ {med:.3f}")
        ax.axvline(g["precoUnitario"].quantile(0.9), color=COR2, ls="--", lw=1.1,
                   label=f"P90 R$ {g['precoUnitario'].quantile(0.9):.3f}")
        ax.set_title(nome.split(",")[0], fontsize=9)
        ax.set_xlabel("preço unitário (R$)")
        ax.legend(fontsize=7, frameon=False)
    axes[0].set_ylabel("nº de itens")
    fig.suptitle("Distribuição do preço unitário por medicamento (escopo comparável)",
                 fontsize=10, fontweight="bold")
    f1 = _salvar(fig, "p1_distribuicao_precos")

    # Preço mediano por UF, normalizado pela mediana nacional do item
    ref = dfp.groupby("codigoItemCatalogo", observed=True)["precoUnitario"].transform("median")
    d = dfp.assign(indice=dfp["precoUnitario"] / ref)
    por_uf = (d.groupby("estado", observed=True)
              .agg(indice_mediano=("indice", "median"), n=("indice", "size"))
              .query("n >= 20").sort_values("indice_mediano"))

    fig2, ax = plt.subplots(figsize=(9, 3.2))
    ax.bar(por_uf.index, (por_uf["indice_mediano"] - 1) * 100,
           color=[COR if v <= 1 else COR2 for v in por_uf["indice_mediano"]])
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("desvio vs mediana\nnacional do item (%)")
    ax.set_title("Nível de preço por UF (índice relativo à mediana nacional de cada medicamento)")
    f2 = _salvar(fig2, "p1_indice_uf")

    return {"tabela": tabela, "decomposicao": decomposicao, "por_uf": por_uf,
            "figuras": [f1, f2]}


# ==========================================================================
# P2 — Existe economia de escala nas compras públicas de medicamentos?
# ==========================================================================


def p2_economia_escala(dfp: pd.DataFrame):
    """Compras maiores obtêm preços unitários menores? Em que magnitude?

    Relevância: é a hipótese que sustenta a política de centralização de
    compras e os consórcios intermunicipais de saúde. Se a elasticidade for
    próxima de zero, fragmentar a compra é barato; se for negativa e
    relevante, a pulverização entre milhares de municípios tem custo fiscal
    mensurável e a agregação é uma recomendação com base empírica.

    Método: regressão log-log
        log(preço) = α + β·log(quantidade) + efeitos de item + efeitos de ano + ε
    β é a elasticidade preço-quantidade. Os efeitos fixos de item CATMAT
    absorvem o nível de preço de cada medicamento (sem eles, β capturaria
    apenas o fato de o AAS ser barato e comprado em grande volume — viés de
    variável omitida); os de ano absorvem inflação e choques de mercado.
    A especificação log-log é a forma funcional canônica para elasticidade e
    também estabiliza a assimetria das duas variáveis.
    Erros-padrão agrupados (cluster) por UASG, porque itens da mesma compra
    e do mesmo comprador não são observações independentes — ignorar isso
    subestimaria os erros-padrão (Moulton, 1990).

    Limitação central, declarada: isto é uma associação, não um efeito causal.
    A quantidade é escolhida pelo comprador, e compradores grandes diferem de
    pequenos em capacidade técnica, poder de barganha e atratividade para o
    fornecedor. β é o gradiente observado, não o retorno de centralizar.
    """
    d = dfp.dropna(subset=["logPrecoUnitario", "logQuantidade", "anoCompra"]).copy()
    d["ano_c"] = d["anoCompra"].astype(int).astype(str)

    modelo = smf.ols(
        "logPrecoUnitario ~ logQuantidade + C(codigoItemCatalogo) + C(ano_c)", data=d
    ).fit(cov_type="cluster", cov_kwds={"groups": d["codigoUasg"]})

    modelo_ampliado = smf.ols(
        "logPrecoUnitario ~ logQuantidade + C(modalidade) + C(forma) + C(esferaDesc)"
        " + C(codigoItemCatalogo) + C(ano_c)", data=d
    ).fit(cov_type="cluster", cov_kwds={"groups": d["codigoUasg"]})

    beta = modelo.params["logQuantidade"]
    ic = modelo.conf_int().loc["logQuantidade"]
    efeitos = {
        "elasticidade": beta,
        "ic95_inf": ic.iloc[0], "ic95_sup": ic.iloc[1],
        "p_valor": modelo.pvalues["logQuantidade"],
        "r2": modelo.rsquared, "n": int(modelo.nobs),
        "efeito_dobrar_qtd_%": 100 * (2 ** beta - 1),
        "efeito_10x_qtd_%": 100 * (10 ** beta - 1),
    }

    por_item = []
    for nome, g in d.groupby("descricaoItem", observed=True):
        m = smf.ols("logPrecoUnitario ~ logQuantidade + C(ano_c)", data=g).fit(
            cov_type="cluster", cov_kwds={"groups": g["codigoUasg"]})
        r = stats.spearmanr(g["quantidade"], g["precoUnitario"])
        por_item.append({
            "item": nome, "n": len(g), "elasticidade": m.params["logQuantidade"],
            "ic95_inf": m.conf_int().loc["logQuantidade"].iloc[0],
            "ic95_sup": m.conf_int().loc["logQuantidade"].iloc[1],
            "spearman": r.statistic, "p_spearman": r.pvalue,
        })
    por_item = pd.DataFrame(por_item)

    # Visão não paramétrica: quintis de quantidade dentro de cada item
    d["quintil_qtd"] = d.groupby("codigoItemCatalogo", observed=True)["quantidade"].transform(
        lambda s: pd.qcut(s, 5, labels=["Q1 (menor)", "Q2", "Q3", "Q4", "Q5 (maior)"], duplicates="drop")
    )
    quintis = d.pivot_table(index="quintil_qtd", columns="descricaoItem",
                            values="precoUnitario", aggfunc="median", observed=True)
    quintis_qtd = d.groupby("quintil_qtd", observed=True)["quantidade"].median()

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=False)
    for ax, (nome, g) in zip(axes, d.groupby("descricaoItem", observed=True)):
        ax.scatter(g["quantidade"], g["precoUnitario"], s=6, alpha=0.3, color=COR)
        xs = np.logspace(np.log10(g["quantidade"].min()), np.log10(g["quantidade"].max()), 50)
        m = smf.ols("logPrecoUnitario ~ logQuantidade", data=g).fit()
        ax.plot(xs, np.exp(m.params["Intercept"] + m.params["logQuantidade"] * np.log(xs)),
                color=COR2, lw=1.8)
        ax.set(xscale="log", yscale="log", xlabel="quantidade (log)",
               title=nome.split(",")[0])
    axes[0].set_ylabel("preço unitário (log, R$)")
    fig.suptitle("Preço unitário vs quantidade adquirida — ajuste log-log",
                 fontsize=10, fontweight="bold")
    f1 = _salvar(fig, "p2_escala")

    fig2, ax = plt.subplots(figsize=(6.4, 3.2))
    (quintis / quintis.iloc[0] * 100).plot(ax=ax, marker="o", lw=1.6)
    ax.set(ylabel="preço mediano\n(Q1 = 100)", xlabel="quintil de quantidade")
    ax.set_title("Preço mediano por quintil de quantidade (dentro de cada medicamento)")
    ax.legend(fontsize=7, frameon=False)
    f2 = _salvar(fig2, "p2_quintis")

    # Consórcios intermunicipais: caso de agregação institucionalizada
    ref = dfp.groupby(["codigoItemCatalogo", "anoCompra"], observed=True)["precoUnitario"].transform("median")
    dd = dfp.assign(razao=dfp["precoUnitario"] / ref)
    consorcios = (dd.groupby("ehConsorcio")
                  .agg(n=("razao", "size"), razao_mediana=("razao", "median"),
                       qtd_mediana=("quantidade", "median")))

    return {"modelo": modelo, "modelo_ampliado": modelo_ampliado, "efeitos": efeitos,
            "por_item": por_item, "quintis": quintis, "quintis_qtd": quintis_qtd,
            "consorcios": consorcios, "figuras": [f1, f2]}


# ==========================================================================
# P3 — O procedimento de contratação está associado ao preço pago?
# ==========================================================================


def p3_procedimento_e_preco(dfp: pd.DataFrame, df_total: pd.DataFrame):
    """Compras por dispensa custam mais que compras por pregão? E quem fornece?

    Relevância: a dispensa de licitação é a exceção legal (Lei 14.133/2021,
    art. 75) e existe para casos de baixo valor ou urgência. Se o preço pago
    por dispensa for sistematicamente maior para um bem idêntico, o uso
    recorrente da exceção tem custo mensurável — e o volume de dispensas por
    ente é um indicador de risco acionável, no espírito da literatura de
    'red flags' em compras públicas (Fazekas & Kocsis, 2020; OCDE, 2016).

    Método: teste de Mann-Whitney-Wilcoxon por medicamento (não paramétrico,
    adequado a distribuições assimétricas e a n muito desiguais entre grupos)
    e o coeficiente de `modalidade` na regressão log-log de P2, que controla
    item, ano, esfera e quantidade — controle necessário porque dispensas
    são, por construção legal, compras pequenas, e compras pequenas já são
    mais caras por P2.

    Concentração de mercado: índice de Herfindahl-Hirschman (HHI) sobre a
    participação em valor por raiz de CNPJ, calculado por medicamento. Faixas
    de referência das diretrizes antitruste (DOJ/FTC; CADE): abaixo de 1.500
    mercado desconcentrado, 1.500-2.500 moderadamente concentrado, acima de
    2.500 concentrado.
    """
    testes = []
    for nome, g in dfp.groupby("descricaoItem", observed=True):
        a = g.loc[g["modalidade"].eq("5"), "precoUnitario"]
        b = g.loc[g["modalidade"].eq("6"), "precoUnitario"]
        if len(b) < 5:
            continue
        u = stats.mannwhitneyu(b, a, alternative="greater")
        # tamanho de efeito: probabilidade de superioridade (Vargha-Delaney A)
        a_vd = u.statistic / (len(a) * len(b))
        testes.append({
            "item": nome, "n_pregao": len(a), "n_dispensa": len(b),
            "mediana_pregao": a.median(), "mediana_dispensa": b.median(),
            "sobrepreco_%": 100 * (b.median() / a.median() - 1),
            "p_valor": u.pvalue, "prob_superioridade": a_vd,
        })
    testes = pd.DataFrame(testes)

    hhi = []
    for nome, g in df_total.groupby("descricaoItem", observed=True):
        share = g.groupby("raizCnpj", observed=True)["valorTotalItem"].sum()
        share = (share / share.sum()).sort_values(ascending=False)
        hhi.append({
            "item": nome, "n_grupos_economicos": len(share),
            "HHI": (share ** 2).sum() * 10_000,
            "CR1_%": 100 * share.iloc[0], "CR4_%": 100 * share.head(4).sum(),
            "lider": g.loc[g["raizCnpj"].eq(share.index[0]), "fornecedorCanonico"].iloc[0],
        })
    hhi = pd.DataFrame(hhi)

    dispensa_por_ente = (
        df_total.assign(disp=df_total["modalidade"].eq("6"))
        .groupby(["nomeUasg", "estado"], observed=True)
        .agg(n_itens=("disp", "size"), n_dispensas=("disp", "sum"),
             valor=("valorTotalItem", "sum"))
        .assign(taxa_dispensa_pct=lambda d: 100 * d["n_dispensas"] / d["n_itens"])
        .query("n_itens >= 3 and n_dispensas > 0")
        .sort_values("taxa_dispensa_pct", ascending=False)
    )

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.3))
    for ax, (nome, g) in zip(axes, dfp.groupby("descricaoItem", observed=True)):
        dados = [g.loc[g["modalidade"].eq(m), "precoUnitario"].dropna() for m in ("5", "6")]
        bp = ax.boxplot(dados, tick_labels=["Pregão", "Dispensa"], patch_artist=True,
                        widths=0.5, showfliers=False)
        for patch, cor in zip(bp["boxes"], [COR, COR2]):
            patch.set_facecolor(cor); patch.set_alpha(0.8)
        for med in bp["medians"]:
            med.set_color("black")
        ax.set_title(f"{nome.split(',')[0]}\n(n={len(dados[0])} vs {len(dados[1])})", fontsize=8.5)
    axes[0].set_ylabel("preço unitário (R$)")
    fig.suptitle("Preço unitário por modalidade de contratação", fontsize=10, fontweight="bold")
    f1 = _salvar(fig, "p3_modalidade")

    fig2, ax = plt.subplots(figsize=(6.2, 3.0))
    ax.bar(hhi["item"].str.split(",").str[0], hhi["HHI"], color=COR)
    for y, rot in [(1500, "desconcentrado / moderado"), (2500, "moderado / concentrado")]:
        ax.axhline(y, color=COR2, ls="--", lw=1)
        ax.text(2.55, y, rot, fontsize=6.5, va="bottom", ha="right", color=COR2)
    ax.set(ylabel="HHI (participação em valor)", ylim=(0, 2800))
    ax.set_title("Concentração de fornecedores por medicamento")
    plt.setp(ax.get_xticklabels(), fontsize=8)
    f2 = _salvar(fig2, "p3_hhi")

    return {"testes": testes, "hhi": hhi, "dispensa_por_ente": dispensa_por_ente,
            "figuras": [f1, f2]}


# ==========================================================================
# Análise complementar: evolução temporal
# ==========================================================================


def p4_serie_temporal(dfp: pd.DataFrame):
    """Como o preço mediano evoluiu ao longo do período coberto?"""
    serie = dfp.pivot_table(index="trimestreCompra", columns="descricaoItem",
                            values="precoUnitario", aggfunc="median")
    n_trim = dfp.groupby("trimestreCompra", observed=True).size().rename("n_itens")

    fig, ax = plt.subplots(figsize=(9, 3.2))
    (serie / serie.iloc[0] * 100).plot(ax=ax, marker="o", ms=3.5, lw=1.4)
    ax.axhline(100, color="black", lw=0.7)
    ax.set(ylabel="índice de preço mediano\n(1º trimestre = 100)", xlabel="")
    ax.set_title("Evolução do preço unitário mediano (valores nominais)")
    ax.legend(fontsize=7, frameon=False)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=7)
    f1 = _salvar(fig, "p4_serie")

    return {"serie": serie, "n_por_trimestre": n_trim, "figuras": [f1]}
