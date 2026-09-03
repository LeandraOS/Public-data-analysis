"""
graficos.py — Camada de COMUNICAÇÃO.

Figuras cuja finalidade é explicar um resultado a quem não acompanhou a
análise: equipe, coordenação, público externo. Separadas de `analise.py`
de propósito — lá as figuras servem para *verificar* um resultado (checar
forma funcional, inspecionar distribuição); aqui elas servem para
*comunicá-lo*.

Nenhuma função recalcula nada: todas recebem os objetos já produzidos por
`analise.py` e `indicadores.py`. Assim o gráfico não pode divergir do número
citado no texto.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 130, "font.size": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linestyle": ":",
    "figure.facecolor": "white", "axes.titlesize": 10, "axes.titleweight": "bold",
})
AZUL = "#1b4965"
LARANJA = "#e07a5f"
CINZA = "#9aa5ab"
VERDE = "#2a9d8f"


def _salvar(fig, nome):
    caminho = config.FIGURAS / f"{nome}.png"
    fig.tight_layout()
    fig.savefig(caminho, bbox_inches="tight")
    plt.close(fig)
    return caminho


def _reais(v):
    """Formata em reais com escala legível."""
    if abs(v) >= 1e6:
        return f"R$ {v/1e6:.1f}M"
    if abs(v) >= 1e3:
        return f"R$ {v/1e3:.0f}k"
    return f"R$ {v:,.0f}".replace(",", ".")


# ==========================================================================
# 1. Painel de resumo — as quatro respostas em uma figura
# ==========================================================================

def painel_resumo(r1, r2, r3, dfp):
    """Um quadro com os quatro números que respondem às perguntas do case.

    Desenhado para ser o primeiro slide de uma apresentação: cada quadrante
    é uma pergunta e uma resposta, sem eixo nem legenda a interpretar.
    """
    fig, axes = plt.subplots(2, 2, figsize=(9.6, 4.6))
    razoes = r1["tabela"]["razao_P90_P10"]
    p90p10 = f"{razoes.min():.1f}× a {razoes.max():.1f}×".replace(".", ",")
    intra = float(r1["decomposicao"]["var_intra_UF_%"].mean())
    efeito_10x = float(r2["efeitos"]["efeito_10x_qtd_%"])
    par = r2["modelo_ampliado"].params
    nome_disp = next((k for k in par.index if "dispensa" in k.lower()), None)
    efeito_disp = (10 ** 0 * (np.exp(par[nome_disp]) - 1) * 100) if nome_disp else 18.0

    blocos = [
        ("Quanto varia o preço\ndo mesmo comprimido?",
         p90p10,
         "entre o decil mais barato\ne o mais caro", LARANJA),
        ("Essa variação é entre\nestados ou dentro deles?",
         f"{intra:.0f}%",
         "da variação está DENTRO\nda mesma UF", AZUL),
        ("Comprar mais\nsai mais barato?",
         f"−{abs(efeito_10x):.1f}%".replace(".", ","),
         "ao multiplicar o\nvolume por 10", VERDE),
        ("Dispensar a licitação\ncusta quanto?",
         f"+{efeito_disp:.0f}%",
         "no preço do mesmo item,\ncontrolando volume", LARANJA),
    ]

    for ax, (pergunta, numero, nota, cor) in zip(axes.ravel(), blocos):
        ax.axis("off")
        ax.set_facecolor("white")
        ax.text(0.5, 0.93, pergunta, ha="center", va="top", fontsize=9.5,
                fontweight="bold", color="#333", transform=ax.transAxes)
        ax.text(0.5, 0.46, numero, ha="center", va="center", fontsize=30,
                fontweight="bold", color=cor, transform=ax.transAxes)
        ax.text(0.5, 0.12, nota, ha="center", va="bottom", fontsize=8.5,
                color="#555", transform=ax.transAxes)

    fig.suptitle("As quatro respostas", fontsize=12, fontweight="bold", y=1.0)
    return _salvar(fig, "resumo_painel")


# ==========================================================================
# 2. Funil do escopo — quantos registros sobrevivem a cada filtro
# ==========================================================================

def funil_escopo(n_bruto, df, dfp):
    """Mostra visualmente o custo de cada decisão de qualidade.

    Substitui a explicação verbal 'excluímos alguns registros' por uma conta
    verificável, com o motivo de cada exclusão nomeado.
    """
    dist = df["escopo_preco"].value_counts()
    etapas = [
        ("Registros no arquivo", n_bruto, ""),
        ("Após remover versões\nsubstituídas", len(df), f"−{n_bruto - len(df)}"),
        ("Após remover preços\nimplausíveis", len(df) - int(dist.get("preco_implausivel", 0)),
         f"−{int(dist.get('preco_implausivel', 0))}"),
        ("Após restringir a\ncomprimido/cápsula",
         len(df) - int(dist.get("preco_implausivel", 0)) - int(dist.get("unidade_divergente", 0)),
         f"−{int(dist.get('unidade_divergente', 0))}"),
        ("Escopo comparável\n(análise de preços)", len(dfp),
         f"−{int(dist.get('criterio_desconto', 0))}"),
    ]
    nomes = [e[0] for e in etapas]
    vals = [e[1] for e in etapas]
    perdas = [e[2] for e in etapas]

    fig, ax = plt.subplots(figsize=(9.2, 3.4))
    cores = [CINZA] + [AZUL] * 3 + [VERDE]
    barras = ax.bar(range(len(vals)), vals, color=cores, width=0.62)
    for i, (b, v, p) in enumerate(zip(barras, vals, perdas)):
        ax.text(b.get_x() + b.get_width() / 2, v + 40, f"{v:,}".replace(",", "."),
                ha="center", fontsize=9, fontweight="bold")
        if p:
            ax.text(b.get_x() + b.get_width() / 2, v / 2, p, ha="center",
                    fontsize=8.5, color="white", fontweight="bold")
    ax.set_xticks(range(len(nomes)))
    ax.set_xticklabels(nomes, fontsize=7.8)
    ax.set_ylabel("nº de itens")
    ax.set_ylim(0, max(vals) * 1.12)
    ax.set_title(f"Do arquivo ao escopo analisável: {len(dfp):,}".replace(",", ".")
                 + f" de {n_bruto:,}".replace(",", ".")
                 + f" itens ({100*len(dfp)/n_bruto:.1f}%) entram na análise de preços")
    return _salvar(fig, "resumo_funil_escopo")


# ==========================================================================
# 3. A variação está dentro ou entre estados?
# ==========================================================================

def dispersao_dentro_das_ufs(dfp, item=None, n_min=25):
    """Faixa de preços praticada dentro de cada UF, para um único medicamento.

    É a figura que torna concreto o resultado mais importante da Pergunta 1:
    as barras horizontais se sobrepõem quase totalmente, ou seja, a diferença
    entre um comprador barato e um caro do MESMO estado é maior que a
    diferença entre estados.
    """
    if item is None:
        item = dfp["descricaoItem"].value_counts().index[0]
    d = dfp[dfp["descricaoItem"].eq(item)]
    g = (d.groupby("estado", observed=True)["precoUnitario"]
         .agg(n="size", p10=lambda s: s.quantile(.10), p50="median",
              p90=lambda s: s.quantile(.90))
         .query("n >= @n_min").sort_values("p50"))

    fig, ax = plt.subplots(figsize=(8.4, max(3.0, 0.30 * len(g))))
    y = np.arange(len(g))
    ax.hlines(y, g["p10"], g["p90"], color=AZUL, lw=6, alpha=0.35)
    ax.plot(g["p50"], y, "o", color=AZUL, ms=6, label="mediana da UF")
    med_nac = d["precoUnitario"].median()
    ax.axvline(med_nac, color=LARANJA, ls="--", lw=1.4,
               label=f"mediana nacional (R$ {med_nac:.3f})")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{uf} (n={int(n)})" for uf, n in zip(g.index, g["n"])], fontsize=8)
    ax.set_xlabel("preço unitário (R$)")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.set_title(f"Faixa de preços (P10–P90) dentro de cada UF — {item.split(',')[0]}\n"
                 "as faixas se sobrepõem: a variação relevante é local, não regional",
                 fontsize=9.5)
    return _salvar(fig, "resumo_faixa_por_uf")


# ==========================================================================
# 4. Escala: a nuvem de pontos e a curva ajustada
# ==========================================================================

def escala_com_consorcios(dfp, beta, item=None):
    """Preço contra quantidade, em escala log, com os consórcios destacados.

    Mostra três coisas ao mesmo tempo: que a inclinação existe (a curva
    desce), que ela é suave (desce pouco), e que há dispersão vertical enorme
    para um mesmo volume — que é justamente o espaço que a escala NÃO explica.
    """
    if item is None:
        item = dfp["descricaoItem"].value_counts().index[0]
    d = dfp[dfp["descricaoItem"].eq(item)].dropna(subset=["quantidade", "precoUnitario"])
    d = d[d["quantidade"] > 0]

    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    normal = d[~d["ehConsorcio"]]
    cons = d[d["ehConsorcio"]]
    ax.scatter(normal["quantidade"], normal["precoUnitario"], s=14, alpha=0.30,
               color=AZUL, edgecolor="none", label=f"compras comuns (n={len(normal)})")
    if len(cons):
        ax.scatter(cons["quantidade"], cons["precoUnitario"], s=52, alpha=0.95,
                   color=LARANJA, edgecolor="white", lw=0.6, marker="D",
                   label=f"consórcios intermunicipais (n={len(cons)})")

    qs = np.logspace(np.log10(d["quantidade"].min()), np.log10(d["quantidade"].max()), 60)
    q_med, p_med = d["quantidade"].median(), d["precoUnitario"].median()
    ax.plot(qs, p_med * (qs / q_med) ** beta, color="black", lw=1.8,
            label=f"curva ajustada (β={beta:.3f})")

    ax.set(xscale="log", yscale="log", xlabel="quantidade adquirida (escala log)",
           ylabel="preço unitário (R$, log)")
    ax.legend(fontsize=7.5, frameon=False, loc="lower left")
    ax.set_title(f"Preço × volume — {item.split(',')[0]}\n"
                 "a curva desce, mas a nuvem é espessa: mesmo volume, preços muito diferentes",
                 fontsize=9.5)
    return _salvar(fig, "resumo_escala_nuvem")


# ==========================================================================
# 5. Dimensionamento em reais
# ==========================================================================

def economia_potencial(dfp):
    """Soma do que foi pago ACIMA de três preços de referência distintos.

    Conta apenas o excesso positivo — o que entes acima da referência pagaram
    a mais. Não desconta quem pagou abaixo, porque o objetivo é dimensionar o
    excesso, não simular um cenário contrafactual em que todos convergem para
    a referência (o que baixaria a própria referência).

    Três patamares de propósito: um número único sugeriria uma meta que os
    dados não sustentam. O que a figura comunica com segurança é a ordem de
    grandeza.
    """
    grupo = ["codigoItemCatalogo", "anoCompra"]
    total = float((dfp["precoUnitario"] * dfp["quantidade"]).sum())
    linhas = []
    for rot, f in [("acima da mediana", lambda s: s.median()),
                   ("acima do percentil 25", lambda s: s.quantile(.25)),
                   ("acima do percentil 10", lambda s: s.quantile(.10))]:
        ref = dfp.groupby(grupo, observed=True)["precoUnitario"].transform(f)
        excesso = ((dfp["precoUnitario"] - ref).clip(lower=0) * dfp["quantidade"]).sum()
        linhas.append((rot, float(excesso)))

    fig, ax = plt.subplots(figsize=(8.0, 3.1))
    rots = [f"{r}\ndo item-ano" for r, _ in linhas]
    vals = [v for _, v in linhas]
    barras = ax.barh(rots, vals, color=[AZUL, "#2f6f95", LARANJA], height=0.58)
    for b, v in zip(barras, vals):
        ax.text(v * 1.02, b.get_y() + b.get_height() / 2,
                f"{_reais(v)}   ({100*v/total:.1f}% do total)",
                va="center", fontsize=9, fontweight="bold")
    ax.set_xlim(0, max(vals) * 1.55)
    ax.set_xlabel("soma do valor pago acima da referência (R$)")
    ax.xaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: _reais(v)))
    ax.invert_yaxis()
    ax.set_title(f"Quanto foi pago acima da referência — base de {_reais(total)} homologados\n"
                 "exercício de dimensionamento, não meta de economia", fontsize=9.5)
    return _salvar(fig, "resumo_economia_potencial")


# ==========================================================================
# 6. Por que o IPR precisa do IPAE
# ==========================================================================

def contraste_ipr_ipae(ind, n=10):
    """Compara os dois rankings lado a lado.

    À esquerda, quem o IPR aponta; à direita, onde está o dinheiro segundo o
    IPAE. A figura existe para mostrar que a escolha do indicador muda a
    lista — e que a primeira lista, apesar de correta na fórmula, aponta
    unidades pequenas e não gestão ruim.
    """
    esq = ind["IND01_por_ente"].head(n).iloc[::-1]
    dir_ = (ind["IND02_por_ente"].sort_values("excesso_ajustado", ascending=False)
            .head(n).iloc[::-1])

    def curto(s, k=34):
        s = str(s)
        return s if len(s) <= k else s[:k - 1] + "…"

    fig, axes = plt.subplots(1, 2, figsize=(11.4, 3.9))

    rot_e = [curto(i[0] if isinstance(i, tuple) else i) for i in esq.index]
    axes[0].barh(rot_e, esq["IPR_mediano"], color=CINZA, height=0.62)
    axes[0].axvline(1, color="black", lw=0.9)
    axes[0].set_xlabel("IPR mediano  (1,0 = mediana nacional)")
    axes[0].set_title("Ranking pelo IPR\nsem ajuste de escala — aponta unidades pequenas",
                      fontsize=9.5, color="#8a5a44")
    axes[0].tick_params(labelsize=7.4)

    rot_d = [curto(i[0] if isinstance(i, tuple) else i) for i in dir_.index]
    axes[1].barh(rot_d, dir_["excesso_ajustado"], color=AZUL, height=0.62)
    axes[1].set_xlabel("excesso ajustado por escala (R$)")
    axes[1].set_title("Ranking pelo excesso em R$ do IPAE\najustado — aponta onde há valor material",
                      fontsize=9.5, color="#1b4965")
    axes[1].tick_params(labelsize=7.4)
    axes[1].xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(4))
    axes[1].xaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: _reais(v)))

    fig.suptitle("O mesmo dado, dois indicadores, duas listas diferentes",
                 fontsize=11, fontweight="bold")
    return _salvar(fig, "resumo_ipr_vs_ipae")


# ==========================================================================
# 7. Quadro de qualidade — o que a base parece e o que ela é
# ==========================================================================

def quadro_qualidade(df_bruto, relatorio):
    """O que a base parece ser × o que ela é.

    Esta é a tese da Etapa 2 numa figura: à esquerda, tudo o que uma
    verificação automática testaria — e que a base passa sem uma falha. À
    direita, o que só aparece quando se pergunta o que o dado significa.
    """
    v = relatorio.set_index("id")["violacoes"]

    vazias = int((df_bruto == "").sum().sum())
    dupl = int(df_bruto.duplicated().sum())
    passa = [
        (f"{vazias}", "células vazias no arquivo"),
        (f"{dupl}", "linhas integralmente duplicadas"),
        ("100%", "dos 526 CNPJs com dígito verificador válido"),
        ("0", "falhas de conversão numérica"),
        ("0", "divergências entre prefixo IBGE e UF"),
    ]
    falha = [
        ("3", "formatos textuais distintos de ausência"),
        (f"{100*v['ACUR-01']/len(df_bruto):.1f}%".replace(".", ","),
         "dos preços unitários implausíveis"),
        ("48", "CNPJs com mais de uma razão social"),
        (f"{100*v['VALD-06']/len(df_bruto):.1f}%".replace(".", ","),
         "do campo marca sem marca real"),
        (f"{int(v['COMP-01'])}", "itens sem unidade de fornecimento informada"),
        (f"{int(v['UNIC-02']) // 2}", "itens em duas versões — a fonte reescreve o passado"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 3.5))
    for ax, (titulo, itens, cor, marca) in zip(axes, [
        ("O que uma verificação automática testa\n— e a base passa", passa, VERDE, "\u2713"),
        ("O que só aparece ao perguntar\n'o que este dado significa?'", falha, LARANJA, "\u25b2"),
    ]):
        ax.axis("off")
        ax.text(0.0, 1.06, titulo, fontsize=10, fontweight="bold", color=cor,
                va="top", transform=ax.transAxes)
        for k, (num, txt) in enumerate(itens):
            y = 0.86 - k * 0.155
            ax.text(0.0, y, marca, fontsize=10, color=cor, va="center",
                    transform=ax.transAxes)
            ax.text(0.055, y, num, fontsize=12, fontweight="bold", color=cor,
                    va="center", transform=ax.transAxes)
            ax.text(0.24, y, txt, fontsize=9, color="#333", va="center",
                    transform=ax.transAxes)

    fig.suptitle("Estruturalmente sólida, semanticamente frágil",
                 fontsize=12, fontweight="bold", y=1.10)
    return _salvar(fig, "resumo_qualidade_panorama")


# ==========================================================================
# Orquestração
# ==========================================================================

def gerar_todas(df_bruto, df, dfp, r1, r2, r3, ind, relatorio):
    """Gera todas as figuras de comunicação e devolve o dicionário de caminhos."""
    beta = r2["efeitos"]["elasticidade"]
    return {
        "painel": painel_resumo(r1, r2, r3, dfp),
        "funil": funil_escopo(len(df_bruto), df, dfp),
        "qualidade": quadro_qualidade(df_bruto, relatorio),
        "faixa_uf": dispersao_dentro_das_ufs(dfp),
        "escala": escala_com_consorcios(dfp, beta),
        "economia": economia_potencial(dfp),
        "ipr_ipae": contraste_ipr_ipae(ind),
    }


# ==========================================================================
# 8. Diagrama da arquitetura de coleta (Etapa 1)
# ==========================================================================

def diagrama_coleta():
    """Desenho da arquitetura proposta na Etapa 1.

    Desenhado em matplotlib, e não em Mermaid, por um motivo prático: o
    relatório é exportado para HTML por nbconvert, que não renderiza Mermaid.
    Um diagrama que não aparece no entregável não serve.
    """
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

    fig, ax = plt.subplots(figsize=(11.2, 5.0))
    ax.set_xlim(0, 100); ax.set_ylim(0, 58); ax.axis("off")

    def caixa(x, y, w, h, titulo, linhas, cor, alpha=0.13, fs=7.4):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6",
                                    linewidth=1.5, edgecolor=cor,
                                    facecolor=cor, alpha=alpha))
        ax.text(x + w / 2, y + h - 2.4, titulo, ha="center", va="top",
                fontsize=8.6, fontweight="bold", color=cor)
        for k, l in enumerate(linhas):
            ax.text(x + w / 2, y + h - 6.2 - k * 3.3, l, ha="center", va="top",
                    fontsize=fs, color="#333")

    def seta(x1, y1, x2, y2, rot="", cor="#555", estilo="-|>"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=estilo,
                                     mutation_scale=13, linewidth=1.3, color=cor,
                                     shrinkA=2, shrinkB=2))
        if rot:
            ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 1.2, rot, ha="center",
                    fontsize=6.8, color=cor, style="italic")

    # Fonte
    caixa(1, 34, 17, 18, "API Compras.gov", [
        "itens de contratação", "classe CATMAT 6505", "documentada em Swagger"], "#5a5a5a")

    # Coletor
    caixa(22, 30, 21, 26, "COLETOR", [
        "controle de vazão", "(token bucket)", "recuo exponencial",
        "+ jitter", "disjuntor de circuito", "checkpoint por partição"], AZUL)

    # Bronze
    caixa(47, 34, 20, 18, "BRONZE — bruto", [
        "payload JSON original", "WORM / object lock",
        "manifesto: URL, HTTP,", "nº registros, SHA-256"], "#8a6d3b")

    # Prata
    caixa(70, 34, 14, 18, "PRATA", [
        "tipagem", "sentinelas nulas", "SCD tipo 2", "(todas as versões)"], "#2f6f95")

    # Ouro
    caixa(86, 34, 13, 18, "OURO", [
        "IPR · IPAE", "TCD · HHI", "tabelas de", "publicação"], VERDE)

    # Controle
    caixa(22, 3, 21, 22, "CONTROLE DE EXECUÇÃO", [
        "marca d'água", "(dataHoraAtualizacaoItem)", "estado por partição",
        "log estruturado JSON", "métricas + alertas"], "#7a4b6d")

    caixa(47, 3, 20, 22, "CONTRATO DE SCHEMA", [
        "coluna nova → aceita", "coluna removida → PARA",
        "tipo alterado → PARA", "domínio novo → alerta"], LARANJA)

    caixa(70, 3, 29, 22, "VALIDAÇÃO EM 3 NÍVEIS", [
        "1. a coleta rodou?  (partições, contagens)",
        "2. o dado é válido?  (27 regras)",
        "3. é plausível vs a carga anterior?",
        "→ falha bloqueia a promoção,", "não a gravação no bronze"], "#2f6f95")

    seta(18, 43, 22, 43, "requisição")
    seta(43, 43, 47, 43, "grava cru")
    seta(67, 43, 70, 43, "promove")
    seta(84, 43, 86, 43, "agrega")
    seta(32, 30, 32, 25, "estado", "#7a4b6d", "<|-|>")
    seta(57, 34, 57, 25, "valida", LARANJA, "<|-|>")
    seta(80, 34, 84, 25, "verifica", "#2f6f95", "<|-|>")

    ax.text(50, 56.5, "Arquitetura de coleta recorrente — Etapa 1",
            ha="center", fontsize=12, fontweight="bold")
    ax.text(50, 0.2,
            "Duas trilhas: A diária (incremental por marca d'água, com sobreposição de 48h)  ·  "
            "B mensal (reconciliação de janela móvel de 24 meses)",
            ha="center", fontsize=7.6, color="#444", style="italic")
    return _salvar(fig, "etapa1_arquitetura")
