# QA Text Auditor

Herramienta Flask determinista para revisar textos en espanol. No usa LLMs ni requiere Java en el modo predeterminado.

## Ejecucion local

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py app.py
```

Abre `http://127.0.0.1:5000`.

## LanguageTool sin Java

El auditor usa `language-tool-python` con `LanguageToolPublicAPI`, que consulta el motor remoto de LanguageTool y no arranca una JVM local.

La API publica tiene limites de uso. Si devuelve un error o esta temporalmente limitada, el sistema conserva los hallazgos deterministas de extranjerismos configurados en `services/spellcheck.py` y no interrumpe la revision.

Para forzar el modo local (requiere Java) solo en una maquina de desarrollo:

```powershell
$env:QA_USE_LOCAL_LANGUAGETOOL = "1"
py app.py
```

## PythonAnywhere gratuito

1. Sube el proyecto incluyendo `templates`, `static`, `services`, `glosario.json` y `requirements.txt`.
2. Crea un entorno virtual desde la consola de PythonAnywhere e instala `pip install -r requirements.txt`.
3. En la configuracion Web, selecciona ese entorno virtual.
4. Usa `app:app` como WSGI application.
5. No instales ni configures Java: el modo publico no lo necesita.

La integracion de Wikipedia y RAE puede requerir salida HTTP habilitada. Si una fuente no responde, la cascada devuelve `Sin resultado factual` sin inventar definiciones.
