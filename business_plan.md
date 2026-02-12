# NetGuru: Plano de Negócios para Plataforma de Orquestração de Rede Agentic (Modelo BYO-LLM)
**Versão:** 2.0 (Estratégia BYO-LLM & Dual RAG)
**Data:** Outubro 2025

---

## 1. Resumo Executivo
O **NetGuru** é uma plataforma de Operações de Rede (NetOps) baseada em Inteligência Artificial "Agentic" (baseada em agentes autônomos). Diferente de soluções tradicionais de monitoramento, o NetGuru atua como um engenheiro virtual de nível sênior, capaz de raciocinar sobre problemas, analisar pacotes brutos (PCAP) e sugerir configurações validadas.

**A Diferenciação Estratégica (BYO-LLM):**
Adotamos um modelo **"Bring Your Own LLM" (Traga seu próprio Modelo)**. A NetGuru fornece a "inteligência de domínio" (RAG especializado em redes Cisco/Multivendor) e a camada de orquestração; o cliente insere sua própria API Key (OpenAI, Azure, Anthropic).
*   **Vantagem Econômica:** Custo marginal de processamento de IA (tokens) é transferido para o cliente, permitindo margens de lucro de software (~85-90%).
*   **Vantagem de Privacidade:** O cliente escolhe onde seus dados são processados (ex: Azure OpenAI privado ou Llama 3 local), superando barreiras de *compliance*.

---

## 2. O Problema e a Solução

### O Problema: "A Crise da Complexidade Operacional"
1.  **Fadiga de Dados:** Redes modernas geram terabytes de logs. Engenheiros perdem horas correlacionando alertas de ferramentas díspares (Splunk, SolarWinds, CLI). O tempo médio de resolução (MTTR) é alto, custando até **US$ 250.000/hora** em inatividade [1].
2.  **Silos de Conhecimento:** A expertise profunda (nível CCIE) é escassa. Engenheiros júnior dependem de escalonamento constante.
3.  **Ferramentas de IA Genéricas:** O ChatGPT "alucina" comandos de rede (inventa sintaxe) e não possui contexto da topologia real do cliente [2, 3].

### A Solução: NetGuru Agentic Platform
Uma interface de chat operacional onde a IA tem acesso a ferramentas reais:
*   **Memória Contextual (RAG):** A IA "lê" a documentação técnica oficial e a topologia do cliente antes de responder.
*   **Agentes Especializados:** Agentes que sabem usar o Wireshark (análise de pacotes), desenhar diagramas e validar conformidade.
*   **Governança:** Nenhuma ação é executada sem validação determinística e aprovação humana ("Human-in-the-loop").

---

## 3. Arquitetura Técnica: O Motor "Dual RAG"

A arquitetura resolve o problema da alucinação e da privacidade dividindo o conhecimento em duas camadas [4, 5]:

### A. Camada de Inferência Agóstica (BYO-Key)
*   **Motor Flexível:** O cliente configura sua chave de API (OpenAI, Anthropic) ou aponta para um endpoint local (Ollama/vLLM).
*   **Privacidade:** Para clientes bancários/governo, suportamos execução 100% local (Air-gapped) com modelos Llama 3 ou Phi-3 [6, 7].

### B. Estratégia "Dual RAG" (O Core IP)
1.  **RAG Global (Curadoria NetGuru):**
    *   Base vetorial proprietária contendo: Manuais de Configuração Cisco/Juniper/Arista, *Design Guides*, CVEs de segurança e soluções de bugs conhecidos.
    *   *Valor:* O cliente "aluga" o acesso a este conhecimento limpo e indexado.
2.  **RAG Local (Dados do Cliente):**
    *   Ingestão segura de arquivos `show tech-support`, diagramas de topologia (Visio/PDF) e tickets antigos.
    *   *Tecnologia:* Uso de **RAPTOR (Recursive Abstractive Processing)** para resumir logs extensos e criar árvores de conhecimento sobre a infraestrutura específica do cliente [8, 9].

### C. Camada de Agentes (Skills)
Utilização de frameworks como LangChain/LlamaIndex para orquestrar ferramentas:
*   **Packet Buddy Agent:** Analisa arquivos `.pcap`. Converte fluxos de pacotes em metadados JSON e pede ao LLM para encontrar anomalias (ex: "Mostre retransmissões TCP no fluxo da aplicação X") [10, 11].
*   **Topology Mapper:** Lê tabelas CDP/LLDP e OSPF de configs enviadas e desenha a topologia visualmente (Mermaid.js/React Flow).
*   **Config Validator:** Compara a sugestão da IA contra regras de "Golden Config" para evitar comandos destrutivos [12, 13].

---

## 4. Funcionalidades do Produto e Roadmap

| Fase | Funcionalidade | Descrição |
| :--- | :--- | :--- |
| **MVP (Mês 1-3)** | **Chatbot Cisco N3** | RAG Global (Docs Cisco). Responde dúvidas de config/tshoot sem alucinar. |
| **MVP** | **Análise de Logs/Config** | Upload de arquivos de texto. IA explica o erro e sugere correção. |
| **Fase 2** | **Agente de Pacotes** | Upload de PCAP. Diagnóstico de latência e perda de pacotes via chat [14]. |
| **Fase 2** | **Topologia Visual** | Desenho automático da rede baseado nos arquivos de config enviados. |
| **Fase 3** | **Integração ITSM** | Conexão com ServiceNow/Jira para abrir/fechar tickets com diagnóstico pronto [15]. |
| **Futuro** | **Execução Ativa (MCP)** | Uso do *Model Context Protocol* para aplicar correções via SSH/Netconf (Requer Agentic Mode) [16, 17]. |

---

## 5. Análise de Mercado e Competitividade

### O Mercado
*   **Tamanho:** O mercado de Automação de Rede deve atingir **US$ 12,38 bilhões até 2030** [18].
*   **Tendência:** A Cisco está movendo todo seu portfólio para "AgenticOps" [19, 20]. O mercado valida que *Agentes* são o futuro, não apenas dashboards.

### Matriz Competitiva

| Concorrente | Modelo | Ponto Forte | Ponto Fraco (Nossa Oportunidade) |
| :--- | :--- | :--- | :--- |
| **Cisco AI Assistant** | Proprietário | Integração nativa profunda. | Caro, exige hardware moderno, focado apenas em Cisco (Vendor-Lockin) [21]. |
| **Selector AI** | SaaS Enterprise | Poderosa análise de telemetria e NLM. | Focado em grandes operadoras, implementação complexa e cara [22]. |
| **ChatGPT / Claude** | Genérico | Acessível e "inteligente". | Alucina comandos técnicos, não lê PCAP nativamente, riscos de privacidade. |
| **NetGuru (Você)** | **SaaS BYO-LLM** | **Custo baixo, Privacidade total, Foco em Engenharia Pura.** | Menor integração nativa inicial (depende de upload de arquivos/logs no MVP). |

---

## 6. Modelo de Negócios e Precificação

Como o custo de inferência é do cliente, adotamos um modelo **SaaS de Alta Margem**.

### Estrutura de Planos (Tiered Pricing)

1.  **Plano "Solo Engineer" (B2C)**
    *   **Público:** Consultores, Estudantes CCIE, Freelancers.
    *   **Preço:** ~$29 - $49 / mês.
    *   **Incluso:** Acesso à Base Global Cisco, Chat ilimitado (chave própria), Agente de Configuração.
    *   **Valor:** "Um mentor CCIE disponível 24/7".

2.  **Plano "Team / MSP" (B2B)**
    *   **Público:** Pequenos MSPs, Equipes de TI médias.
    *   **Preço:** ~$199 / mês (base) + $X por usuário adicional.
    *   **Incluso:** RAG Local Compartilhado (Time vê os mesmos docs/topologias), Agente PCAP (Packet Buddy), Gestão de Projetos.
    *   **Diferencial:** Colaboração em tempo real no troubleshooting.

3.  **Plano "Enterprise / Self-Hosted"**
    *   **Público:** Bancos, Governo, Utilities.
    *   **Preço:** Licença Anual ($25k - $50k+).
    *   **Entrega:** Container Docker/Kubernetes rodando na infra do cliente (On-Prem). Suporte a modelos locais open-source.
    *   **Diferencial:** Auditoria total, RBAC, Integração ServiceNow/NetBox.

---

## 7. Estratégia de Go-to-Market (Lançamento)

### Canais de Aquisição
1.  **Comunidades Técnicas (Guerilla Marketing):** Lançar ferramentas gratuitas (ex: um "Validador de Config Cisco" simples) no Reddit (r/networking), GNS3 e EVE-NG para capturar leads qualificados.
2.  **Parcerias com MSPs:** Oferecer o NetGuru como ferramenta "White Label" para MSPs melhorarem seus SLAs de atendimento.
3.  **Marketplaces:** Listar no AWS Marketplace e Azure Marketplace para facilitar a compra corporativa [23].

### Estratégia de Conteúdo
*   Publicar estudos de caso: "Como diagnosticamos um problema de STP em 2 minutos usando NetGuru vs 4 horas manualmente".
*   Vídeos demonstrando a análise de PCAP (Packet Buddy) – o efeito "uau" visual [10].

---

## 8. Projeção Financeira Simplificada (Estimativa Ano 1)

*   **Custos Iniciais (CAPEX/Desenvolvimento):**
    *   Desenvolvimento MVP (3 Engenheiros x 4 meses): ~$120k - $150k.
    *   Infraestrutura (Cloud/Vetores): ~$2k/mês (baixo devido ao modelo BYO-LLM).
*   **Receita Projetada:**
    *   Meta: 500 usuários Solo ($40/mês) + 20 Times MSP ($500/mês).
    *   Receita Mensal Recorrente (MRR) final do Ano 1: ~$30.000.
*   **Ponto de Equilíbrio (Break-even):** Estimado entre o mês 9 e 12.

---

## 9. Próximos Passos (Plano de Ação Imediato)

1.  **Desenvolver Protótipo (PoC):** Criar um script Python que usa a API da OpenAI + LangChain para ler um arquivo PDF da Cisco e responder perguntas técnicas com precisão (Validar o RAG).
2.  **Validar o "Packet Buddy":** Implementar a funcionalidade de leitura de PCAP usando a biblioteca `pyshark` e enviar o resumo para o LLM [24].
3.  **Landing Page:** Criar site capturando e-mails para lista de espera ("Otimize seu NOC com sua própria IA").