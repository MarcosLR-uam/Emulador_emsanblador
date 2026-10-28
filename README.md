# BitLab · Emulador de ensamblador de 2 bits

Proyecto web educativo en Python Flask. Interfaz en español, registros A/B,
flags ZF/CF/SF/OF, ejecución completa o por pasos, etiquetas, historial y descarga
del código como `.asm`. No necesita base de datos, claves ni servicios externos.

## Ejecutar localmente

Requiere Python 3.10 o posterior; la configuración de Render usa Python 3.13.2.
Abrí una terminal dentro de la carpeta que contiene `app.py`.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

En macOS/Linux, activá el entorno con `source .venv/bin/activate`.
Si PowerShell bloquea la activación, usá directamente
`.venv\Scripts\python.exe -m pip install -r requirements.txt` y
`.venv\Scripts\python.exe app.py`.

Abrí http://127.0.0.1:5000. El servidor local tiene el modo debug desactivado.
Gunicorn se instala únicamente en sistemas distintos de Windows y se usa en Render.

## Pruebas

```sh
python -m unittest discover -s tests -v
```

Las pruebas recorren todas las combinaciones de operandos de 2 bits para suma,
resta, comparación, operaciones lógicas y saltos condicionales. También comprueban
INC/DEC, historial, aislamiento de solicitudes, errores y límites.

## Uso

1. Elegí un ejemplo o escribí el programa.
2. Pulsá **Paso a paso** para ejecutar una instrucción o **Ejecutar** para continuar
   hasta terminar o alcanzar el límite global de 2.000 instrucciones ejecutadas.
3. Consultá registros, flags, próxima línea y estados del historial.
4. **Reiniciar** conserva el código y devuelve la CPU a cero. Editar el código o
   cambiar de ejemplo también reinicia la ejecución.

El PC identifica instrucciones desde cero (no cuenta comentarios ni etiquetas).
Las líneas del historial sí corresponden al texto original. La interfaz muestra el
estado posterior; la API incluye estados anterior y posterior. El historial existe
durante la sesión de la página; al recargar se pierde. Descargar `.asm` guarda el código.

## Modelo de CPU

Es una arquitectura educativa inspirada en convenciones de x86, no un emulador
binario x86. Registros y flags empiezan en cero. El PC no está limitado a 2 bits.

| Bits | Sin signo | Con signo (complemento a dos) |
|---|---:|---:|
| 00 | 0 | 0 |
| 01 | 1 | 1 |
| 10 | 2 | -2 |
| 11 | 3 | -1 |

Los resultados se reducen módulo 4. Un inmediato decimal admite −2…3 y un binario
`0b00`…`0b11`; se normalizan al patrón de 2 bits. No hay memoria ni pila.
Las instrucciones y etiquetas no distinguen mayúsculas. Una etiqueta comienza
con letra ASCII o `_` y continúa con letras, dígitos o `_`. Debe ser única.
Se admite una etiqueta por línea, sola o antes de una instrucción.
Los comentarios empiezan con `;`. No se usa `eval` ni se ejecuta código Python ingresado.

| Instrucción | Operación |
|---|---|
| `MOV A, B` | Copia fuente a destino; conserva todos los flags |
| `ADD A, 1` | Suma y actualiza los cuatro flags |
| `SUB A, B` | Resta y actualiza los cuatro flags |
| `CMP A, B` | Actualiza flags como SUB; conserva registros |
| `AND A, B`, `OR A, B`, `XOR A, B` | Operación lógica; ZF/SF según resultado, CF=OF=0 |
| `INC A`, `DEC B` | Suma/resta 1; actualiza ZF/SF/OF y conserva CF |
| `JC destino` | Salta cuando CF=1 (acarreo o préstamo) |
| `JGE destino` | Salta cuando SF=OF; comparación **con signo** |
| `JE destino` | Salta cuando ZF=1 |
| `JNE destino` | Salta cuando ZF=0 |
| `JMP destino` | Salta siempre |
| `HLT` | Detiene la ejecución |

En instrucciones de dos operandos, el primero debe ser A/B y el segundo un
registro o inmediato; deben separarse con coma. Los saltos solo admiten etiquetas.
Llegar al final del programa también detiene la CPU, incluso mediante un salto a
una etiqueta situada al final. HLT y los saltos conservan los flags.

- **ZF**: el resultado truncado es cero.
- **SF**: el bit alto del resultado truncado es 1.
- **CF**: acarreo en suma (resultado sin truncar >3); préstamo en resta (izquierdo < derecho sin signo).
- **OF**: el resultado matemático de la operación con signo queda fuera de −2…1.

Por ejemplo, `1 + 1` produce `10`, SF=1 y OF=1; `3 + 1` produce `00`, ZF=1 y CF=1.
`CMP A, B` y `JGE` comparan patrones como valores con signo: `11` es −1, no 3.

```asm
MOV A, 0
MOV B, 3
bucle:
INC A
DEC B
CMP B, 0
JNE bucle
HLT
```

Resultado: A=11 (3 sin signo, −1 con signo), B=00.

## API

`POST /api/execute` recibe JSON:

```json
{"code": "MOV A, 3\nADD A, 1\nHLT", "steps": 2}
```

`steps` es el total de instrucciones a reproducir **desde cero**, no un incremento.
Es opcional; por defecto vale 2.000. Para avanzar enviá 1, luego 2, luego 3… con el
mismo código. La aplicación reconstruye una CPU independiente por solicitud;
no guarda estados globales ni confía en registros recibidos del cliente. Esto permite
usar múltiples trabajadores de Gunicorn sin mezclar usuarios. Ejecutar todo después
de varios pasos reproduce el prefijo y continúa de forma determinista.

Respuesta: `registers`, `flags`, `pc`, `halted`, `steps`, `next_line`, `program`,
`history` y `limit_reached`. Cada entrada del historial incluye instrucción, línea y
snapshots `before`/`after`. Un bucle que alcanza 2.000 pasos devuelve HTTP 200 con
`limit_reached: true` y el historial disponible. Un programa finito que termina
exactamente en ese paso no se considera limitado.

Errores de entrada: HTTP 400 y `{"error": "descripción"}`; cuerpo demasiado grande:
HTTP 413. Límites: 20.000 caracteres, 500 instrucciones, 100.000 bytes por solicitud.
`GET /health` devuelve `{"status":"ok"}`. No existe persistencia ni autenticación.

## Subir a GitHub

Descomprimí el ZIP y subí **el contenido** de `emulador-2bits` al repositorio:
`app.py`, `emulator.py`, `templates/`, `tests/`, `requirements.txt`, `render.yaml`,
`README.md` y `.gitignore`. `app.py` y `render.yaml` deben quedar en la raíz del repositorio.
No subas `.venv`, archivos `.env` ni cachés.

También podés crear un repositorio vacío en GitHub y ejecutar en la carpeta:

```sh
git init
git add .
git commit -m "Crear emulador de ensamblador de 2 bits"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
git push -u origin main
```

Reemplazá usuario y repositorio por tus datos.

## Desplegar en Render

1. Subí el proyecto a GitHub.
2. En Render elegí **New > Blueprint**, conectá el repositorio y revisá el servicio
   definido por `render.yaml` antes de confirmar su creación.
3. Esperá a que finalice el despliegue y abrí la dirección asignada por Render.

Alternativa: **New > Web Service**, conectá GitHub, elegí Python y configurá:

| Campo | Valor |
|---|---|
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 30 app:app` |
| Health Check Path | `/health` |
| Variable de entorno | `PYTHON_VERSION=3.13.2` |

Si dejaste el proyecto dentro de una subcarpeta del repositorio, configurá esa
carpeta como Root Directory; preferiblemente usá la estructura raíz indicada.
El plan solicitado en el YAML es `free`; revisá su disponibilidad y condiciones
en tu cuenta. No se crean cuentas ni se publica automáticamente al descargar el ZIP.

Referencias oficiales consultadas el 28 de octubre de 2026:
[Flask en Render](https://render.com/docs/deploy-flask) y
[Blueprint YAML](https://render.com/docs/blueprint-spec).
