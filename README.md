# Punto Verde Express — Bot para WhatsApp

Bot prototipo creado para la Actividad 1 de Design Thinking.

## Funciones
- Menú de lunes a viernes según el informe.
- Sábado: solamente parrillas.
- Pedido guiado: entrada, segundo, recojo/delivery, hora y confirmación.
- Estado del último pedido.
- Opción de atención humana.
- Guarda pedidos localmente en SQLite.
- Incluye una demo web en `/demo` para ensayarlo antes de conectarlo a WhatsApp.

## Probarlo primero sin WhatsApp
1. Instala Python 3.10 o superior.
2. Abre una terminal dentro de la carpeta.
3. Ejecuta:

```bash
python -m venv .venv
```

En Windows:
```bash
.venv\Scripts\activate
```

Luego:
```bash
pip install -r requirements.txt
python app.py
```

Abre en el navegador:
`http://127.0.0.1:5000/demo`

## Conectarlo a WhatsApp Cloud API
La integración usa la API oficial de WhatsApp Business Platform de Meta.

Necesitas en Meta:
- Access Token.
- Phone Number ID.
- Una versión válida de Graph API.
- App Secret (recomendado).
- Un Verify Token elegido por ti.

Copia `.env.example` como `.env` y completa:

```env
VERIFY_TOKEN=punto-verde-verificacion
WHATSAPP_ACCESS_TOKEN=TU_TOKEN
WHATSAPP_PHONE_NUMBER_ID=TU_PHONE_NUMBER_ID
GRAPH_API_VERSION=LA_VERSION_QUE_MUESTRE_META
META_APP_SECRET=TU_APP_SECRET
```

Tu servidor debe estar publicado en HTTPS. En Meta configura el callback como:
`https://TU-DOMINIO/webhook`

y usa el mismo `VERIFY_TOKEN`.

## Precios
El informe todavía no fija precios, así que el bot no inventa montos. Cuando los definan, completa:

```env
MENU_PRICE=S/ 12.00
DELIVERY_FEE=S/ 3.00
SATURDAY_GRILL_PRICE=S/ 20.00
```

Si quedan vacíos, el bot mostrará “por confirmar”.

## Evidencia para el informe
Prueba el flujo con un estudiante y un trabajador. Guarda capturas de bienvenida, menú, selección, modalidad, resumen y confirmación. Luego completa la tabla de validación de la Actividad 1.
