# FinStatement — Analisador Financeiro Buffett

> Chega de copiar e colar de PDF para Excel.
> Suba o RI, receba o Buffett Score, a planilha exportada e a análise fundamentalista — tudo em menos de 30 segundos.

<!-- SCREENSHOT 1 ─────────────────────────────────────────────────────────────
   O quê: resultado completo na aba "Buffett Score" com uma empresa conhecida
   (Petrobras ou Magazine Luiza funcionam bem por serem reconhecíveis).
   Deve mostrar: o gauge animado com o score, os indicadores-chave no lado
   direito e pelo menos 4–5 métricas na lista abaixo.
   Formato sugerido: GIF de 5–8s capturando a animação do gauge enchendo,
   ou PNG estático se preferir simplicidade. Dimensão: 1200×700px.
────────────────────────────────────────────────────────────────────────────-->

<img width="1526" height="633" alt="capturaFinStatement" src="https://github.com/user-attachments/assets/54507930-664c-48f6-8bf9-8ef5e95eb0ba" />



## O problema

Todo analista que acompanha empresas listadas conhece o ritual: baixar o PDF do RI, abrir o Excel, copiar Receita Líquida, Lucro Bruto e Patrimônio Líquido linha por linha, calcular margens na mão, e só então começar a pensar se o negócio é bom ou não.

O FinStatement elimina esse trabalho mecânico. Você arrasta o PDF e em segundos tem as demonstrações financeiras estruturadas, 12 métricas do framework de Buffett pontuadas automaticamente e uma planilha Excel pronta para uso.

Para quem quiser ir além dos números brutos, o sistema oferece análise narrativa opcional via IA — SWOT, Porter e veredito de investimento — gerada pelo modelo de linguagem de sua escolha e ancorada nos dados extraídos do próprio PDF.

---

## O que ele NÃO é


- **Não é uma plataforma SaaS.** Não tem dados históricos, gráficos de cotação nem comparação entre empresas. Roda localmente, no seu computador.
- **Não substitui o analista.** O Buffett Score e a análise de IA são pontos de partida, não decisão de compra. A ferramenta lê o que está no PDF — se a empresa omitir o FCO ou divulgar apenas métricas ajustadas (non-GAAP), o sistema pontua com o que tem e indica os campos ausentes como N/D.
- **PDFs escaneados não são suportados.** O pipeline extrai texto com coordenadas; imagens não têm texto selecionável. Confirme que consegue selecionar texto no PDF antes de usar.
- **A análise de IA depende da extração.** Em PDFs com layout incomum, alguns campos podem ficar N/D, e a análise narrativa refletirá essa limitação com honestidade.

---

## Instalação

### Pré-requisitos

- Python 3.9 ou superior
- Nenhuma conta, nenhum cadastro, nenhuma assinatura

### Passos

```bash
# 1. Clonar o repositório
git clone https://github.com/Huarada/finstatement.git
cd finstatement/backend

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Subir o servidor
python server.py
```

Abra **http://localhost:8000** no browser. Não há mais nenhum passo.

---

## Como usar

### Interface web

<!-- SCREENSHOT 2 ─────────────────────────────────────────────────────────────
   O quê: a tela de upload com o seletor de provedor de IA visível.
   Deve mostrar: a zona de drag-and-drop, os botões de provedor (Auto-detect,
   Claude, GPT-4o, Gemini) e o campo de API Key.
   Objetivo: mostrar que é simples — uma tela, um botão.
   Formato sugerido: PNG estático, 1200×500px.
────────────────────────────────────────────────────────────────────────────-->
![finStatementGUiaInserirPDFV2](https://github.com/user-attachments/assets/58640bae-c6c0-49c1-a2e7-b7c8376c8859)


1. Arraste ou selecione o PDF (DFP, ITR ou Earnings Release)
2. **Sem API Key:** clique em Analisar — Buffett Score e planilha Excel em ~2 segundos
3. **Com API Key (opcional):** selecione o provedor, cole a chave e clique em Analisar — análise narrativa em ~20–30 segundos adicionais

O resultado aparece imediatamente após a extração — você não precisa esperar a IA para ver os dados financeiros.

### Via linha de comando

```bash
# Extração sem IA
curl -X POST http://localhost:8000/api/v1/analyze \
  -F "file=@PETR4_DFP_2025.pdf"

# Com análise IA — Claude
curl -X POST http://localhost:8000/api/v1/analyze/insights \
  -F "file=@PETR4_DFP_2025.pdf" \
  --F "api_key=$ANTHROPIC_API_KEY" \
  -F "provider=anthropic"

# Com análise IA — OpenAI
curl -X POST http://localhost:8000/api/v1/analyze/insights \
  -F "file=@MGLU_ER_4T25.pdf" \
  -F "api_key=$OpenAI_API_KEY" \
  -F "provider=openai"
```

---

## O que você recebe

### Buffett Score

Pontuação de 0 a 100 baseada em 12 métricas para empresas industriais (ou 7 para bancos), derivadas do livro *Warren Buffett and the Interpretation of Financial Statements* (Mary Buffett & David Clark, 2008). Cada métrica é clicável e mostra a explicação do capítulo correspondente.

| Score | Diagnóstico |
|---|---|
| 90–100 | Vantagem Competitiva Durável (Moat Forte) |
| 70–89 | Vantagem Competitiva Moderada |
| 50–69 | Negócio Razoável / Sem Moat Claro |
| 30–49 | Negócio Commodity / Alta Competição |
| 0–29 | Evitar — Fundamentos Fracos |

### Demonstrações financeiras

DRE, Balanço Patrimonial e métricas bancárias (quando aplicável) com valores extraídos e normalizados para R$ Milhões. A anualização é automática: se o PDF for de um earnings release com coluna 12M, o sistema detecta e não multiplica por 4 erroneamente.

### Tabelas brutas

Todas as tabelas detectadas no PDF, navegáveis diretamente na interface. Útil para conferir se a extração pegou os dados certos em PDFs com layout incomum, e para auditoria dos valores que alimentaram o score.

### Análise de IA

<!-- SCREENSHOT 3 ─────────────────────────────────────────────────────────────
   O quê: a aba "Análise IA" com o veredito e as métricas de decisão visíveis.
   Deve mostrar: o badge COMPRAR/AGUARDAR/VENDER, as três barras de Risco /
   Crescimento / Confiabilidade com os textos de justificativa numérica abaixo
   de cada uma, e o início da seção de Destaques.
   Objetivo: mostrar que a IA cita números reais, não texto genérico.
   Formato sugerido: PNG estático ou GIF com scroll, 1200×800px.
────────────────────────────────────────────────────────────────────────────-->
![analysisModel_V3](https://github.com/user-attachments/assets/5f158dee-8f92-4b82-943d-6524447d13f9)


Análise narrativa gerada pelo modelo de sua escolha, ancorada nos números extraídos do PDF:

- **Destaques e desafios do período** — com nível de confiança por item e citação da tabela de origem
- **Análise SWOT** — cada item deve citar um número do relatório; itens genéricos são bloqueados pelo prompt
- **5 Forças de Porter** — com comentário setorial por força e concorrentes reais do setor
- **Métricas de Decisão** — Nível de Risco, Perspectiva de Crescimento e Confiabilidade do RI, com score 1–10 e justificativa baseada nos dados extraídos
- **Veredito** — COMPRAR / AGUARDAR / VENDER com nível de confiança (ALTA / MÉDIA / BAIXA)

A IA não inventa dados. O prompt é construído com os números já extraídos e instruído a citar valores específicos em cada campo. Se um dado estiver ausente, o score reflete a incerteza em vez de preencher com texto genérico.

### Exportação Excel

Um `.xlsx` com abas separadas para resumo, demonstrações financeiras, cada tabela extraída do PDF (DRE, Balanço, DFC, KPIs…), Buffett Score completo com benchmarks e, quando disponível, a análise de IA.

---

## Análise de IA — provedores suportados

A API Key é detectada automaticamente pelo prefixo. Você traz sua própria chave; o FinStatement não armazena nada além do necessário para a chamada ao provedor.

| Prefixo | Provedor | Modelo |
|---|---|---|
| `sk-ant-` | Anthropic | claude-sonnet-4-20250514 |
| `sk-` | OpenAI | gpt-4o |
| `AIza` | Google | gemini-1.5-flash |

**Custo estimado por análise:** ~$0.04 (Claude) · ~$0.06 (GPT-4o) · ~$0.01 (Gemini Flash)

**Onde obter chaves:** [Anthropic](https://console.anthropic.com) · [OpenAI](https://platform.openai.com/api-keys) · [Google](https://aistudio.google.com/app/apikey)

---

## PDFs suportados e testados

| Empresa | Ticker | Tipo |
|---|---|---|
| Magazine Luiza | MGLU3 | Earnings Release 4T |
| Petrobras | PETR4 | DFP / ITR |
| Suzano | SUZB3 | DFP / ITR |
| BTG Pactual | BPAC11 | Demonstrações IFRS |
| Banco do Brasil | BBAS3 | Destaques Gerenciais |
| Itaú Unibanco | ITUB4 | DFP |
| Ambev | ABEV3 | DFP |

PDFs disponíveis em: site de RI de cada empresa · [B3](https://www.b3.com.br) · [CVM](https://www.rad.cvm.gov.br)

---

## Arquitetura

```
finstatement/
├── backend/
│   ├── server.py                    # Entrypoint Flask
│   ├── requirements.txt
│   └── app/
│       ├── api/main.py              # Rotas HTTP + serialização
│       ├── application/
│       │   ├── analyze_pdf.py       # Orquestrador principal
│       │   ├── generate_ai.py       # Análise narrativa via IA
│       │   └── ai_providers.py      # Adapters Claude/GPT/Gemini (Strategy Pattern)
│       ├── domain/
│       │   ├── entities.py          # Dataclasses imutáveis
│       │   ├── parsers/             # Resolução de colunas e linhas
│       │   └── scoring/buffett.py   # Engine de scoring
│       └── infrastructure/pdf/
│           └── extractor.py         # Pipeline L1→L4 (pdfplumber)
└── frontend/
    └── index.html                   # SPA completo (vanilla JS, sem framework)
```

**Pipeline L1→L4:**

```
PDF bytes
  L1 → pdfplumber extrai palavras com coordenadas X/Y
  L2 → agrupa em linhas, detecta limites de colunas por posição de header,
        monta matriz de texto
  L3 → classifica cada bloco (DRE, Balanço, DFC, KPIs…) por assinatura semântica
  L4 → split de mega-tabelas, deduplicação, conversão para entidades de domínio
```

Os dados extraídos passam por schemas **Pydantic v2** que descartam valores com inconsistências contábeis — por exemplo, lucro líquido maior que 5× a receita — antes de chegarem ao scoring.

---

## Testes

```bash
cd backend
python -m pytest tests/ -v
```

109 testes cobrindo extração de PDF, scoring, classificação semântica de tabelas, resolução de colunas e adapters de IA (com mocks — sem chamadas reais à API).

---

## Variáveis de ambiente

Todas têm valores padrão funcionais. Nenhuma é obrigatória para rodar.

| Variável | Padrão | Descrição |
|---|---|---|
| `PORT` | `8000` | Porta do servidor |
| `DEBUG` | `false` | Modo debug Flask |
| `ANTHROPIC_API_KEY` | `""` | Chave padrão (pode ser passada pela UI em vez de aqui) |
| `AI_MAX_TOKENS` | `4096` | Tokens máximos por resposta de IA |
| `MAX_PDF_SIZE_MB` | `50` | Tamanho máximo de PDF aceito |

---

## Troubleshooting

**"Empresa não identificada"** — O nome de marca não foi reconhecido nas primeiras 5 páginas. Os dados financeiros são extraídos normalmente. Para adicionar uma empresa, inclua o padrão em `_COMPANY_BRAND_PATS` no `extractor.py`.

**Score 0/100 com todos os campos N/D** — O PDF provavelmente é escaneado. Tente selecionar texto nele para confirmar. PDFs de imagem não são suportados.

**Valores 4× maiores que o esperado** — Verifique `effective_af` no debug (aba Tabelas → Debug info). Abra a aba Tabelas e confira os nomes das colunas da DRE para confirmar se a coluna anual foi detectada corretamente.

**"JSON inválido" na análise de IA** — A resposta foi truncada. Aumente `AI_MAX_TOKENS` para `6000` via variável de ambiente.

---

## Contribuindo

PRs são bem-vindos, especialmente para suporte a novos layouts de PDF, correções de padrões de extração e novos provedores de IA. Se encontrar um PDF que extrai errado, abra uma issue com o nome da empresa, o tipo de documento e quais campos ficaram N/D.

---

*FinStatement não constitui recomendação de investimento. Os dados são extraídos dos documentos fornecidos pelo usuário e não são verificados de forma independente.*
