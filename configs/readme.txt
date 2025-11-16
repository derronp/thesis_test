to select provider, copt contents of llm_xyz.json to llm.json

Set your key:
Windows (PowerShell): setx OPENAI_API_KEY "sk-..." then restart the terminal
Linux/macOS: export OPENAI_API_KEY="sk-..."
(If you prefer, you can put "api_key": "sk-..." under "openai" in the JSON instead of using env vars.)


if using "api_key_env": "OPENAI_API_KEY" make sure to set api key in terminal as shown above
if you want to set key manually, replace "api_key_env" with "api_key": "sk-your-real-openai-api-key-here"