# MDM Server — Fase 2

Backend FastAPI que recebe checkins dos agentes Windows,
armazena inventário e gerencia comandos remotos.

## Estrutura

```
mdm-server/
├── main.py          # Rotas da API (FastAPI)
├── database.py      # Banco de dados SQLite
├── requirements.txt
├── Dockerfile
└── README.md
```

## Rodar localmente (teste)

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Acesse http://localhost:8000/docs para ver a documentação interativa.

## Deploy gratuito no Railway

1. Crie conta em https://railway.app
2. Clique em "New Project" → "Deploy from GitHub"
3. Suba este projeto num repositório GitHub
4. Railway detecta o Dockerfile automaticamente
5. Vá em "Variables" e adicione:
   - `ADMIN_USER` = seu_usuario
   - `ADMIN_PASS` = sua_senha_forte
   - `DB_PATH`    = /data/mdm.db
6. Em "Volumes", crie um volume em `/data` (para o banco persistir)
7. Copie a URL gerada (ex: https://mdm-server-xxx.railway.app)

## Deploy gratuito no Render

1. Crie conta em https://render.com
2. New → Web Service → conecte seu GitHub
3. Runtime: Docker
4. Adicione as variáveis de ambiente (ADMIN_USER, ADMIN_PASS)
5. Adicione um Disk em /data para persistência

## Endpoints da API

### Agente (autenticado por token do dispositivo)
| Método | Rota                            | Descrição                  |
|--------|---------------------------------|----------------------------|
| POST   | /api/enroll                     | Registro inicial do PC     |
| POST   | /api/checkin                    | Envia inventário            |
| GET    | /api/commands/pending           | Busca comandos pendentes   |
| POST   | /api/commands/{id}/result       | Reporta resultado          |

### Painel admin (usuário/senha HTTP Basic)
| Método | Rota                                    | Descrição                    |
|--------|-----------------------------------------|------------------------------|
| GET    | /api/admin/devices                      | Lista todos os dispositivos  |
| GET    | /api/admin/devices/{id}                 | Detalhe do dispositivo       |
| GET    | /api/admin/devices/{id}/inventory       | Inventário completo          |
| GET    | /api/admin/devices/{id}/commands        | Histórico de comandos        |
| POST   | /api/admin/devices/{id}/commands        | Envia comando                |
| DELETE | /api/admin/devices/{id}                 | Remove dispositivo           |
| GET    | /api/admin/stats                        | Estatísticas gerais          |

### Tipos de comando disponíveis
| type            | payload           | Ação                          |
|-----------------|-------------------|-------------------------------|
| run_script      | código PowerShell | Executa script no PC          |
| install_app     | ID do Winget      | Instala aplicativo            |
| uninstall_app   | ID do Winget      | Remove aplicativo             |
| apply_patches   | (vazio)           | Aplica Windows Update         |
| reboot          | segundos (opt.)   | Reinicia o PC                 |
| get_inventory   | (vazio)           | Força coleta de inventário    |

## Variáveis de ambiente

| Variável    | Padrão               | Descrição              |
|-------------|----------------------|------------------------|
| ADMIN_USER  | admin                | Usuário do painel      |
| ADMIN_PASS  | troque-esta-senha    | Senha do painel        |
| DB_PATH     | mdm.db               | Caminho do banco SQLite|

## Próximo passo — Fase 3

Com o servidor no ar, edite o agente PowerShell (Fase 1):
- Abra `Install-MDMAgent.ps1`
- Troque `https://SEU-SERVIDOR.com` pela URL do Railway/Render
- Reinstale o agente nos PCs

Depois parta para a Fase 3: painel web React para visualizar
tudo e enviar comandos com interface gráfica.
