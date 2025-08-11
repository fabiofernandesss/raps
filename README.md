# Sistema RAPS - Aplicação Web

Este projeto implementa uma aplicação web simples com formulário de dados e armazenamento local.

## Funcionalidades

- Interface web moderna e responsiva
- Formulário para cadastro de dados (Nome, Email, Descrição)
- Armazenamento local usando localStorage
- Visualização dos dados salvos
- Design moderno com gradientes e animações

## Tecnologias

- HTML5
- CSS3 (com Flexbox e Grid)
- JavaScript (ES6+)
- LocalStorage para persistência de dados

## Como usar

1. Clone o repositório:
```bash
git clone https://github.com/fabiofernandesss/raps.git
cd raps
```

2. Abra o arquivo `index.html` em qualquer navegador web moderno.

## Funcionalidades da Aplicação

- **Formulário de Cadastro**: Permite inserir nome, email e descrição
- **Validação**: Campos obrigatórios com validação HTML5
- **Armazenamento**: Dados salvos localmente no navegador
- **Visualização**: Lista todos os dados salvos com timestamp
- **Interface Responsiva**: Funciona em desktop e dispositivos móveis

## Estrutura do Projeto

```
raps/
├── index.html          # Aplicação web principal
├── .gitignore         # Arquivos ignorados pelo Git
└── README.md          # Este arquivo
```

## Banco de Dados

A aplicação utiliza o localStorage do navegador como banco de dados local. Os dados são persistidos entre sessões e incluem:
- ID único (timestamp)
- Nome do usuário
- Email
- Descrição
- Data e hora do cadastro