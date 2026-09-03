"""
inserir_celulas_comunicacao.py

Insere no notebook as células de comunicação: as respostas em linguagem
direta, as figuras de `src/graficos.py` e os blocos "em uma frase" ao final
de cada pergunta.

Idempotente: identifica os pontos de inserção por marcador textual e não
duplica células já inseridas (checa a etiqueta MARCA).
"""
import nbformat as nbf

CAMINHO = "notebooks/case_compras_medicamentos.ipynb"
MARCA = "<!-- celula-comunicacao -->"

nb = nbf.read(CAMINHO, as_version=4)

if any(MARCA in c.source for c in nb.cells):
    raise SystemExit("Células de comunicação já presentes — nada a fazer.")


def md(texto):
    return nbf.v4.new_markdown_cell(MARCA + "\n" + texto)


def code(texto):
    return nbf.v4.new_code_cell(texto)


def indice_da_celula(prefixo, tipo="markdown", ocorrencia=0):
    """Índice da célula cujo início casa com o prefixo."""
    achados = [i for i, c in enumerate(nb.cells)
               if c.cell_type == tipo
               and c.source.lstrip().lstrip("-").lstrip().startswith(prefixo)]
    if not achados:
        raise KeyError(f"não encontrei célula começando com {prefixo!r}")
    return achados[ocorrencia]


# =====================================================================
# BLOCO A — "As respostas, em linguagem direta", logo após o título
# =====================================================================

A_MD = md("""
## As respostas, em linguagem direta

Esta seção existe para responder às perguntas do case **sem jargão**, antes
de qualquer método. Todo número aqui é reproduzido e discutido adiante; o
rigor está nas seções seguintes, a clareza está nesta.

### 1. Os dados são confiáveis?

**Parcialmente — e o risco está onde ninguém olha.** A base parece
impecável: nenhuma célula vazia, nenhuma linha duplicada, todos os 526 CNPJs
válidos. Qualquer verificação automática a aprovaria. Mas quando se pergunta
o que cada dado *significa*, aparecem problemas que mudariam conclusões:
preços que na verdade são o valor do lote inteiro, a mesma empresa contada
como três fornecedores diferentes, e um campo de "ausência" gravado em três
formatos distintos — um deles um simples espaço, invisível numa tabela.

**O que fizemos:** nada foi apagado. Cada registro problemático recebeu uma
etiqueta, e as exclusões acontecem no momento da análise, de forma explícita
e reversível. Dos 2.706 itens, **2.455 (90,8%)** entram na comparação de
preços.

### 2. O preço pago pelo mesmo medicamento varia muito?

**Sim — cerca de duas vezes.** Comparando exatamente o mesmo produto (mesmo
código de catálogo, mesma apresentação), um comprador no grupo mais caro paga
**1,8 a 2,3 vezes** o que paga um comprador no grupo mais barato.

**O detalhe que muda a interpretação:** a maior parte dessa variação
(**~86%**) acontece **dentro do mesmo estado**, entre entes vizinhos. Não é
custo de frete nem diferença de mercado regional — é diferença de capacidade
de comprar bem.

### 3. Comprar em maior quantidade sai mais barato?

**Sim, mas menos do que se imagina.** Multiplicar o volume por dez reduz o
preço unitário em cerca de **14%** — não pela metade. Os **consórcios
intermunicipais** de saúde pagam cerca de **20% abaixo** da mediana, o que é
a evidência mais concreta de que juntar compras funciona.

**Por que isso importa:** serve como antídoto a duas conclusões erradas
opostas — "centralizar resolve tudo" (não resolve: são 14%) e "escala é
irrelevante" (é relevante e mensurável).

### 4. A forma de contratar faz diferença?

**Sim: dispensar a licitação custa cerca de 18% a mais.** Comparando o mesmo
medicamento, no mesmo ano, em volumes semelhantes, as compras feitas por
dispensa saem **18% mais caras**. No caso do AAS, a diferença bruta chega a
70%.

### 5. Falta concorrência entre os fornecedores?

**Não.** Cada medicamento tem quase **300 grupos econômicos** distintos
fornecendo, e os índices de concentração ficam todos na faixa considerada
desconcentrada. O mercado é competitivo.

---

### A conclusão que amarra tudo

Junte as três últimas respostas:

> Os preços variam muito (2×), a escala explica pouco dessa variação (14%) e
> **não** falta concorrência entre os fornecedores.

Por eliminação, **o problema está do lado de quem compra, não de quem
vende.**

Essa é a conclusão mais importante do trabalho, e ela é uma **boa notícia**.
Se a causa fosse cartel ou concentração de mercado, o remédio seria lento,
caro e fora do alcance de um gestor de saúde. Sendo diferença de capacidade
de compra num mercado onde o preço baixo já existe e está disponível, os
instrumentos são conhecidos e testados:

1. **dar ao gestor acesso ao preço de referência** — é o que os indicadores
   propostos na Etapa 5 fazem;
2. **agregar demanda via consórcio**, que os dados mostram funcionando;
3. **reduzir a dispensa** onde a demanda é previsível, como é o caso de
   genéricos de uso contínuo.

### Quanto dinheiro está em jogo?

Nos três medicamentos desta base, o valor pago **acima da mediana** do
próprio grupo soma **R$ 617 mil**; acima do percentil 25, **R$ 1,6 milhão**;
acima do percentil 10, **R$ 4,2 milhões** — sobre R$ 49,4 milhões
homologados.

São **três medicamentos genéricos** num recorte parcial da compra pública.
Trato esses valores como ordem de grandeza, não como meta: parte da diferença
é escala legítima e parte é urgência real.
""")

A_NOTA = md("""
> As figuras de comunicação desta seção são geradas por
> `src/graficos.py`, um módulo separado de `analise.py` de propósito: lá as
> figuras servem para **verificar** um resultado, aqui para **comunicá-lo**.
> Nenhuma delas recalcula nada — todas recebem os objetos já produzidos pela
> análise, de modo que a figura não pode divergir do número citado no texto.
> O quadro-resumo com as quatro respostas aparece ao final da Etapa 4, quando
> os quatro resultados já foram estabelecidos.
""")

B_MD = md("""
### As quatro respostas em um quadro

Fecho a Etapa 4 com a figura desenhada para abrir uma apresentação: quatro
perguntas, quatro números, nenhum eixo para interpretar.
""")

B_CODE = code("""from src import graficos

display(Image(str(graficos.painel_resumo(r1, r2, r3, dfp))))""")

# =====================================================================
# BLOCO C — panorama de qualidade (seção 2)
# =====================================================================

C_MD = md("""
### O panorama de qualidade em uma figura

A figura abaixo é a tese desta seção. À esquerda, tudo o que uma verificação
automática de qualidade testaria — e que esta base passa sem uma única falha.
À direita, o que só aparece quando se pergunta o que o dado significa.

**A leitura prática:** um relatório de qualidade que só olhasse a coluna da
esquerda concluiria que a base está pronta para uso. Ela não está.
""")

C_CODE = code("""from src import graficos

display(Image(str(graficos.quadro_qualidade(df_bruto, relatorio))))""")

# =====================================================================
# BLOCO D — funil do escopo (seção 3)
# =====================================================================

D_MD = md("""
### Quantos dados sobrevivem a cada decisão

Toda decisão de qualidade custa registros, e esse custo deve ser explícito.
A figura mostra o caminho do arquivo até a base analisável, com o motivo de
cada exclusão nomeado.

**Como ler:** o número no topo de cada barra é quanto sobrou; o número dentro
da barra é quanto saiu naquela etapa. A perda total é de **9,2%** — e
nenhuma linha foi de fato apagada: todas seguem na base, marcadas.
""")

D_CODE = code("""display(Image(str(graficos.funil_escopo(len(df_bruto), df, dfp))))""")

# =====================================================================
# BLOCO E — faixa por UF (Pergunta 1)
# =====================================================================

E_MD = md("""
### A figura que mostra por que a variação é local

Cada barra é a faixa de preços (do percentil 10 ao 90) praticada **dentro de
uma mesma UF** para o mesmo medicamento; o ponto é a mediana da UF e a linha
tracejada é a mediana nacional.

**O que salta aos olhos:** as barras se **sobrepõem quase completamente**. As
medianas estaduais são praticamente iguais — variam entre R$ 0,04 e R$ 0,06 —
mas cada estado, isoladamente, contém compradores pagando de R$ 0,03 a
R$ 0,08.

**Em uma frase:** a diferença entre dois compradores do mesmo estado é maior
que a diferença entre estados. É isso que a decomposição de variância diz em
números, e é isso que desloca o diagnóstico de "custo regional" para
"capacidade de compra local".
""")

E_CODE = code("""display(Image(str(graficos.dispersao_dentro_das_ufs(dfp))))""")

# =====================================================================
# BLOCO F — nuvem de escala (Pergunta 2)
# =====================================================================

F_MD = md("""
### A economia de escala vista sem estatística

Cada ponto é uma compra: quantidade no eixo horizontal, preço unitário no
vertical, ambos em escala logarítmica (necessária porque as quantidades vão
de 1 a 71 milhões). A linha preta é a curva ajustada; os losangos são os
consórcios intermunicipais.

**Três leituras, em ordem de importância:**

1. **A curva desce** — existe economia de escala, e ela é visível a olho nu.
2. **A curva desce pouco** — atravessa oito ordens de magnitude de volume
   caindo pouco mais de uma vez e meia em preço. É a modéstia do −14%.
3. **A nuvem é espessa** — e este é o ponto central: para um *mesmo* volume,
   há compras a R$ 0,03 e a R$ 0,08. Essa espessura vertical é exatamente a
   variação que a escala **não** explica, e é onde vive o problema de gestão.

**Em uma frase:** o volume explica parte do preço, mas a dispersão vertical
mostra que dois entes comprando a mesma quantidade ainda podem pagar preços
muito diferentes.
""")

F_CODE = code("""display(Image(str(
    graficos.escala_com_consorcios(dfp, r2["efeitos"]["elasticidade"]))))""")

# =====================================================================
# BLOCO G — dimensionamento (após Pergunta 3)
# =====================================================================

G_MD = md("""
### Quanto isso representa em reais

Traduzir dispersão de preço em dinheiro é o que torna o achado utilizável por
quem decide. A figura soma, para cada patamar de referência, **apenas o
excesso** — o que os entes que pagaram acima da referência pagaram a mais.

**Por que três patamares e não um número:** um valor único sugeriria uma meta
de economia que os dados não sustentam. Nem todo ente pode pagar o percentil
10 — parte da diferença é escala legítima, parte é urgência real. O que a
figura comunica com segurança é a **ordem de grandeza**: centenas de milhares
a alguns milhões de reais, em **três medicamentos genéricos**.
""")

G_CODE = code("""display(Image(str(graficos.economia_potencial(dfp))))""")

# =====================================================================
# BLOCO H — contraste IPR/IPAE (seção 5)
# =====================================================================

H_MD = md("""
### Por que dois indicadores, e não um

Os dois painéis usam **os mesmos dados** e produzem **listas completamente
diferentes**.

À esquerda, o ranking pelo IPR, sem ajuste de escala: o topo é dominado por
hospitais militares e unidades pequenas. Eles pagam, de fato, acima da
mediana nacional — mas pela razão mais banal possível: **compram poucas
centenas de comprimidos**. O indicador, aqui, está medindo porte e chamando
isso de ineficiência.

À direita, o ranking pelo excesso em reais do IPAE, que desconta o efeito do
volume e pondera pelo valor: aparecem grandes compradores, onde há dinheiro
material em jogo.

**Em uma frase:** publicar o ranking da esquerda seria tecnicamente errado e
reputacionalmente arriscado — apontaria como ineficientes órgãos cujo único
desvio é o tamanho. O ranking da direita responde à pergunta que interessa:
onde está o excesso que dá para recuperar.

Este contraste é, na minha leitura, o resultado metodológico mais
transferível do case: **a validação de um indicador inclui olhar quem ele
coloca no topo e perguntar se aquilo faz sentido.**
""")

H_CODE = code("""display(Image(str(graficos.contraste_ipr_ipae(ind))))""")

# =====================================================================
# Inserções — de baixo para cima, para não invalidar os índices
# =====================================================================

insercoes = [
    # (índice de referência, deslocamento, células)
    (indice_da_celula("## IND-02 — Índice de Preço Ajustado por Escala"), 1,
     [H_MD, H_CODE]),
    (indice_da_celula("### Resultados", ocorrencia=2), 1,
     [G_MD, G_CODE, B_MD, B_CODE]),
    (indice_da_celula("### Resultados", ocorrencia=1), 1, [F_MD, F_CODE]),
    (indice_da_celula("### Resultados", ocorrencia=0), 1, [E_MD, E_CODE]),
    (indice_da_celula("**Advertência sobre"), 1, [D_MD, D_CODE]),
    (indice_da_celula("### Interpretação dos achados"), 1, [C_MD, C_CODE]),
    (indice_da_celula("## 0. Ambiente e dependências"), 0, [A_MD, A_NOTA]),
]

for idx, desloc, celulas in insercoes:
    pos = idx + desloc
    nb.cells[pos:pos] = celulas

nbf.write(nb, CAMINHO)
print(f"Inseridas {sum(len(c) for _, _, c in insercoes)} células. "
      f"Total agora: {len(nb.cells)}")
