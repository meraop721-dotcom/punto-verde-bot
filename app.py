import os, json, sqlite3, hmac, hashlib, uuid, time, html
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from flask import Flask, request, jsonify, Response, render_template_string
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
VERIFY_TOKEN=os.getenv('VERIFY_TOKEN','punto-verde-verificacion')
ACCESS_TOKEN=os.getenv('WHATSAPP_ACCESS_TOKEN','')
PHONE_NUMBER_ID=os.getenv('WHATSAPP_PHONE_NUMBER_ID','')
GRAPH_API_VERSION=os.getenv('GRAPH_API_VERSION','')
APP_SECRET=os.getenv('META_APP_SECRET','')
MENU_PRICE=os.getenv('MENU_PRICE','12.00').strip()
DELIVERY_FEE_GUADALUPE=os.getenv('DELIVERY_FEE_GUADALUPE','3.00').strip()
DELIVERY_FEE_CHEPEN=os.getenv('DELIVERY_FEE_CHEPEN','5.00').strip()
SATURDAY_GRILL_PRICE=os.getenv('SATURDAY_GRILL_PRICE','').strip()
ADMIN_KEY=os.getenv('ADMIN_KEY','puntoverde123').strip()
YAPE_NUMBER=os.getenv('YAPE_NUMBER','921780382').strip()
YAPE_HOLDER=os.getenv('YAPE_HOLDER','Oscar Jean Pierre Mera Sanchez').strip()
ADMIN_WHATSAPP_NUMBER=os.getenv('ADMIN_WHATSAPP_NUMBER','').strip()
WAIA_API_KEY=os.getenv('WAIA_API_KEY','').strip()
WAIA_CONNECTION_ID=os.getenv('WAIA_CONNECTION_ID','').strip()
WAIA_WEBHOOK_TOKEN=os.getenv('WAIA_WEBHOOK_TOKEN','').strip()
WAIA_WEBHOOK_SECRET=os.getenv('WAIA_WEBHOOK_SECRET','').strip()
DB_PATH=os.getenv('DB_PATH','punto_verde.db')
UPLOAD_DIR=os.getenv('UPLOAD_DIR','/tmp/punto_verde_uploads')
TZ=ZoneInfo('America/Lima')

MENUS={
0:{'dia':'Lunes','entradas':['Sopa de menestrón','Tamales','Crema de rocoto'],'segundos':['Ají de gallina','Lentejitas con pescado apanado','Tallarines con chuleta']},
1:{'dia':'Martes','entradas':['Chilcana criolla','Papa rellena','Papa a la huancaína'],'segundos':['Seco de res con frejol','Pollo al horno con ensalada rusa','Pollo broaster']},
2:{'dia':'Miércoles','entradas':['Caldo de gallina','Pastel de choclo','Anticuchos'],'segundos':['Puré con lonza en salsa agridulce','Arroz con pollo','Lomo saltado']},
3:{'dia':'Jueves','entradas':['Caldo de mote','Crema de ocopa','Causa de pollo'],'segundos':['Cau-cau','Saltado de coliflor','Escabeche de pollo']},
4:{'dia':'Viernes','entradas':['Empanadas de carne','Parihuela','Causa de atún'],'segundos':['Milanesa de pollo','Escabeche de pescado','Chaufa de pescado']},
}

def money(value):
    try:
        return f"S/ {float(value):.2f}"
    except Exception:
        return f"S/ {value}" if value else 'por confirmar'

def delivery_fee(zone):
    if zone == 'Guadalupe':
        return DELIVERY_FEE_GUADALUPE
    if zone == 'Chepén':
        return DELIVERY_FEE_CHEPEN
    return '0.00'

def total_amount(mode, zone=None):
    try:
        base=float(MENU_PRICE)
        delivery=float(delivery_fee(zone)) if mode=='Delivery' else 0.0
        return money(base+delivery)
    except Exception:
        return 'por confirmar'

def total_numeric(mode, zone=None):
    try:
        base=float(MENU_PRICE)
        delivery=float(delivery_fee(zone)) if mode=='Delivery' else 0.0
        return base+delivery
    except Exception:
        return None

def order_summary(data):
    zone=data.get('zona')
    delivery_value=money(delivery_fee(zone)) if data.get('modo')=='Delivery' else 'S/ 0.00'
    total=total_amount(data.get('modo'),zone)

    location=''
    if data.get('modo')=='Delivery':
        location=(
            f"\nZona: {data.get('zona','')}\n"
            f"Dirección: {data.get('direccion','')}"
        )

    payment=f"\n💳 Pago: {data.get('pago','')}"
    if data.get('pago')=='Yape':
        if data.get('comprobante_yape'):
            payment += "\n📸 Comprobante: recibido (pendiente de verificación)"
    elif data.get('pago')=='Efectivo':
        payment += f"\nPaga con: {data.get('efectivo_entrega','')}"
        if data.get('vuelto'):
            payment += f"\nVuelto aprox.: {data.get('vuelto')}"

    return (
        "🧾 *RESUMEN DEL PEDIDO*\n\n"
        f"👤 Cliente: {data.get('cliente','')}\n"
        f"Entrada: {data.get('entrada','')}\n"
        f"Segundo: {data.get('segundo','')}\n"
        f"Modalidad: {data.get('modo','')}"
        f"{location}\n"
        f"Hora: {data.get('hora','')}\n\n"
        f"💵 Precio: {money(MENU_PRICE)}\n"
        f"🚚 Delivery: {delivery_value}\n"
        f"💰 *TOTAL: {total}*"
        f"{payment}\n\n"
        "1️⃣ Sí, confirmar\n"
        "2️⃣ No, cancelar"
    )

MAIN=("🌿 *PUNTO VERDE EXPRESS* 🌿\nMenús & Parrillas\n\n¡Hola! 👋 ¿Qué deseas hacer?\n"
      "1️⃣ Ver menú de hoy\n2️⃣ Hacer un pedido\n3️⃣ Parrillas del sábado\n4️⃣ Estado de mi pedido\n5️⃣ Hablar con una persona\n\nResponde con el número de una opción.")

DEMO='''<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Punto Verde Express</title>
<style>
body{font-family:Arial;background:#efeae2;margin:0}
.w{max-width:430px;height:760px;margin:18px auto;background:white;display:flex;flex-direction:column;border-radius:18px;overflow:hidden;box-shadow:0 5px 25px #999}
.h{background:#075e54;color:white;padding:16px;font-weight:bold}
.c{flex:1;padding:14px;overflow:auto;background:#efeae2}
.m{white-space:pre-wrap;padding:9px 11px;border-radius:10px;margin:7px 0;max-width:82%;background:white}
.me{margin-left:auto;background:#d9fdd3}
.b{display:flex;gap:8px;padding:10px;background:#f0f2f5;align-items:center}
.b input[type=text]{flex:1;border:0;border-radius:20px;padding:12px;min-width:0}
.b button,.photo{border:0;border-radius:20px;background:#00a884;color:white;padding:11px 14px;cursor:pointer}
.photo{background:#54656f}
#f{display:none}
</style>
<div class="w">
  <div class="h">Punto Verde Express<br><small>Prototipo del bot</small></div>
  <div id="c" class="c"></div>
  <div class="b">
    <label class="photo" for="f">📷</label>
    <input id="f" type="file" accept="image/*" onchange="img()">
    <input id="i" type="text" placeholder="Escribe 1, 2, 3...">
    <button onclick="s()">Enviar</button>
  </div>
</div>
<script>
const c=document.getElementById('c'),i=document.getElementById('i'),f=document.getElementById('f');
function a(t,k){let d=document.createElement('div');d.className='m '+k;d.textContent=t;c.appendChild(d);c.scrollTop=c.scrollHeight}
async function s(){
  let t=i.value.trim(); if(!t)return;
  a(t,'me'); i.value='';
  let r=await fetch('/demo-message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
  let j=await r.json(); a(j.reply,'')
}
async function img(){
  if(!f.files.length)return;
  a('📷 Comprobante de Yape enviado','me');
  let fd=new FormData(); fd.append('image',f.files[0]);
  let r=await fetch('/demo-image',{method:'POST',body:fd});
  let j=await r.json(); a(j.reply,''); f.value=''
}
i.onkeydown=e=>{if(e.key==='Enter')s()};
fetch('/demo-message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'hola',reset:true})})
.then(r=>r.json()).then(j=>a(j.reply,''));
</script>'''

def db():
    conn=sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS sessions(phone TEXT PRIMARY KEY,state TEXT,data TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,phone TEXT,details TEXT,status TEXT,created_at TEXT)')
    cols=[r[1] for r in conn.execute('PRAGMA table_info(orders)').fetchall()]
    if 'updated_at' not in cols:
        conn.execute('ALTER TABLE orders ADD COLUMN updated_at TEXT')
        conn.execute('UPDATE orders SET updated_at=created_at WHERE updated_at IS NULL')
    conn.execute('CREATE TABLE IF NOT EXISTS processed_events(delivery_id TEXT PRIMARY KEY,created_at TEXT)')
    conn.commit()
    return conn

def sess(phone):
    with db() as c:
        r=c.execute('SELECT state,data FROM sessions WHERE phone=?',(phone,)).fetchone()
    return (r[0],json.loads(r[1] or '{}')) if r else ('main',{})

def setsess(phone,state,data=None):
    with db() as c:
        c.execute('INSERT INTO sessions VALUES(?,?,?) ON CONFLICT(phone) DO UPDATE SET state=excluded.state,data=excluded.data',(phone,state,json.dumps(data or {},ensure_ascii=False)))
        c.commit()

def event_seen(delivery_id):
    if not delivery_id:
        return False
    with db() as c:
        try:
            c.execute('INSERT INTO processed_events(delivery_id,created_at) VALUES(?,?)',(delivery_id,datetime.now(TZ).isoformat()))
            c.commit()
            return False
        except sqlite3.IntegrityError:
            return True

def new_order(phone,details):
    details=dict(details or {})
    if details.get('pago')=='Yape':
        details.setdefault('pago_estado','Pendiente de verificación')
    elif details.get('pago')=='Efectivo':
        details.setdefault('pago_estado','Pago al entregar')
    now=datetime.now(TZ).isoformat()
    with db() as c:
        q=c.execute(
            'INSERT INTO orders(phone,details,status,created_at,updated_at) VALUES(?,?,?,?,?)',
            (phone,json.dumps(details,ensure_ascii=False),'Pedido recibido',now,now)
        )
        c.commit()
        oid=q.lastrowid
    notify_admin_new_order(oid,phone,details)
    return oid

def last_order(phone):
    with db() as c:
        return c.execute(
            'SELECT id,status,details,created_at,updated_at FROM orders WHERE phone=? ORDER BY id DESC LIMIT 1',
            (phone,)
        ).fetchone()

def get_order(order_id, phone=None):
    with db() as c:
        if phone:
            return c.execute(
                'SELECT id,phone,details,status,created_at,updated_at FROM orders WHERE id=? AND phone=?',
                (order_id,phone)
            ).fetchone()
        return c.execute(
            'SELECT id,phone,details,status,created_at,updated_at FROM orders WHERE id=?',
            (order_id,)
        ).fetchone()

def update_order_status(order_id,status):
    with db() as c:
        c.execute(
            'UPDATE orders SET status=?,updated_at=? WHERE id=?',
            (status,datetime.now(TZ).isoformat(),order_id)
        )
        c.commit()


def order_payment_status(details):
    if details.get('pago')=='Yape':
        return details.get('pago_estado','Pendiente de verificación')
    if details.get('pago')=='Efectivo':
        return details.get('pago_estado','Pago al entregar')
    return details.get('pago_estado','Sin registrar')

def update_payment_status(order_id,payment_status):
    order=get_order(order_id)
    if not order:
        return None
    oid,phone,details_json,status,created_at,updated_at=order
    try:
        details=json.loads(details_json or '{}')
    except Exception:
        details={}
    details['pago_estado']=payment_status
    new_status=status
    if payment_status=='Pago verificado' and status=='Pedido recibido':
        new_status='Confirmado'
    with db() as c:
        c.execute(
            'UPDATE orders SET details=?,status=?,updated_at=? WHERE id=?',
            (json.dumps(details,ensure_ascii=False),new_status,datetime.now(TZ).isoformat(),order_id)
        )
        c.commit()
    return phone,details,new_status

def notify_admin_new_order(order_id,phone,details):
    if not ADMIN_WHATSAPP_NUMBER:
        return
    try:
        name=details.get('cliente','Cliente')
        items=' + '.join(x for x in [details.get('entrada'),details.get('segundo')] if x) or details.get('tipo','Pedido')
        total=total_amount(details.get('modo'),details.get('zona'))
        send_text(ADMIN_WHATSAPP_NUMBER,f'🔔 *NUEVO PEDIDO #{order_id}*\n👤 {name}\n🍽️ {items}\n💰 {total}\n💳 {details.get("pago","Sin registrar")}')
    except Exception as e:
        app.logger.warning('No se pudo avisar al administrador: %s',e)

TRACK_STEPS=[
    ('Pedido recibido','🧾'),
    ('Confirmado','✅'),
    ('En preparación','👨‍🍳'),
    ('Listo para recojo','🥡'),
    ('En camino','🛵'),
    ('Entregado','🏁'),
]

def tracking_text(order):
    oid,phone,details_json,status,created_at,updated_at=order
    try:
        details=json.loads(details_json or '{}')
    except Exception:
        details={}
    names=[x[0] for x in TRACK_STEPS]
    idx=names.index(status) if status in names else -1
    lines=[]
    for i,(name,icon) in enumerate(TRACK_STEPS):
        if status=='Cancelado': mark='○'
        elif i < idx: mark='✅'
        elif i == idx: mark='➡️'
        else: mark='○'
        lines.append(f'{mark} {icon} {name}')
    if status=='Cancelado':
        lines.append('❌ Pedido cancelado')
    customer=f"\n👤 Cliente: {details.get('cliente','')}" if details.get('cliente') else ''
    if details.get('modo')=='Delivery':
        extra=f"\n📍 {details.get('zona','')} — {details.get('direccion','')}"
    else:
        extra='\n📍 Modalidad: Recojo'
    payment=order_payment_status(details)
    return (
        f"📦 *SEGUIMIENTO DEL PEDIDO #{oid}*" + customer + "\n\n" + "\n".join(lines)
        + f"\n\nEstado actual: *{status}*"
        + f"\n💳 Pago: *{payment}*"
        + extra + "\n\nEscribe *0* para volver al menú."
    )

def menu_text(day=None):
    day=datetime.now(TZ).weekday() if day is None else day
    if day in MENUS:
        m=MENUS[day]; e='\n'.join(f'{i+1}. {x}' for i,x in enumerate(m['entradas'])); s='\n'.join(f'{i+1}. {x}' for i,x in enumerate(m['segundos']))
        p=f'Precio del almuerzo: {money(MENU_PRICE)}'
        return f"🍽️ *MENÚ DEL {m['dia'].upper()}*\n\n*Entradas*\n{e}\n\n*Segundos*\n{s}\n\n💰 {p}\n\nPara ordenar, responde *2*."
    if day==5:
        p=SATURDAY_GRILL_PRICE or 'por confirmar'
        return f'🔥 *ESPECIAL DE SÁBADO: PARRILLAS*\n\nLos sábados ofrecemos únicamente parrillas.\nPrecio: {p}\n\nEscribe *RESERVAR* para dejar una reserva o *0* para volver.'
    return '🌿 Hoy es domingo y no tenemos atención programada. Escribe *0* para volver.'

def reply(phone,text,force_day=None):
    raw=(text or '').strip(); t=raw.lower()
    if t in {'hola','inicio','menú','menu','0','volver','cancelar'}:
        setsess(phone,'main',{}); return MAIN
    state,data=sess(phone)
    if state=='main':
        if t=='1': return menu_text(force_day)
        if t=='2':
            d=datetime.now(TZ).weekday() if force_day is None else force_day
            if d in MENUS:
                m=MENUS[d]; setsess(phone,'entrada',{'day':d}); opts='\n'.join(f'{i+1}. {x}' for i,x in enumerate(m['entradas']))
                return f"🥣 Elige tu entrada para el {m['dia']}:\n{opts}\n\nResponde 1, 2 o 3."
            if d==5: setsess(phone,'parrilla',{}); return '🔥 Hoy solo ofrecemos parrillas. Escribe tu nombre y la hora aproximada. Ejemplo: Andrea, 1:00 p. m.'
            return 'Hoy no hay atención programada. Escribe *0* para volver.'
        if t=='3': return menu_text(5)
        if t=='4':
            o=last_order(phone)
            if not o:
                return '📦 Aún no tienes pedidos registrados. Escribe *0* para volver.'
            setsess(phone,'track_order',{})
            return f'📦 Tu último pedido es el *#{o[0]}*.\n\nEscribe el número de pedido que deseas consultar.\nEjemplo: *{o[0]}*'
        if t=='5': return '👤 Un integrante del equipo continuará la conversación cuando sea necesario. Escribe *0* para volver.'
        if t=='reservar': setsess(phone,'parrilla',{}); return '🔥 Escribe tu nombre y la hora aproximada para la reserva. Ejemplo: Carlos, 1:30 p. m.'
        return 'No pude reconocer esa opción.\n\n'+MAIN
    if state=='track_order':
        if not t.isdigit():
            return 'Escribe solo el número de pedido. Ejemplo: *1*.'
        order=get_order(int(t),phone)
        if not order:
            return 'No encontré ese pedido asociado a este número. Intenta nuevamente o escribe *0* para volver.'
        setsess(phone,'main',{})
        return tracking_text(order)

    if state=='entrada':
        if t not in {'1','2','3'}: return 'Responde solo *1, 2 o 3* para elegir la entrada.'
        m=MENUS[data['day']]; data['entrada']=m['entradas'][int(t)-1]; setsess(phone,'segundo',data); opts='\n'.join(f'{i+1}. {x}' for i,x in enumerate(m['segundos']))
        return f"✅ Entrada: *{data['entrada']}*\n\n🍛 Elige tu segundo:\n{opts}\n\nResponde 1, 2 o 3."
    if state=='segundo':
        if t not in {'1','2','3'}:
            return 'Responde solo *1, 2 o 3* para elegir el segundo.'
        m=MENUS[data['day']]
        data['segundo']=m['segundos'][int(t)-1]
        setsess(phone,'nombre_cliente',data)
        return (
            f"✅ Segundo: *{data['segundo']}*\n\n"
            "👤 ¿A nombre de quién estará el pedido?\n"
            "Escribe nombre y apellido.\n"
            "Ejemplo: *Andrea López*"
        )

    if state=='nombre_cliente':
        if len(raw) < 3:
            return 'Escribe un nombre válido, por ejemplo: *Andrea López*.'
        data['cliente']=raw
        setsess(phone,'modo',data)
        return (
            f"Gracias, *{data['cliente']}*.\n\n"
            "¿Cómo deseas recibir tu pedido?\n"
            "1️⃣ Recojo\n"
            "2️⃣ Delivery"
        )
    if state=='modo':
        if t not in {'1','2'}:
            return 'Responde *1* para recojo o *2* para delivery.'
        data['modo']='Recojo' if t=='1' else 'Delivery'
        if data['modo']=='Delivery':
            setsess(phone,'zona_delivery',data)
            return (
                '📍 ¿A qué zona será el delivery?\n\n'
                f'1️⃣ Guadalupe — {money(DELIVERY_FEE_GUADALUPE)}\n'
                f'2️⃣ Chepén — {money(DELIVERY_FEE_CHEPEN)}\n\n'
                'Responde 1 o 2.'
            )
        setsess(phone,'hora',data)
        return '🕐 ¿A qué hora aproximadamente deseas recoger tu pedido? Ejemplo: 1:15 p. m.'

    if state=='zona_delivery':
        if t not in {'1','2'}:
            return 'Responde *1* para Guadalupe o *2* para Chepén.'
        data['zona']='Guadalupe' if t=='1' else 'Chepén'
        setsess(phone,'direccion_delivery',data)
        return (
            f'📌 Delivery para *{data["zona"]}*.\n'
            'Escribe la dirección exacta y una referencia breve.\n\n'
            'Ejemplo: Jr. Lima 245, frente a la farmacia.'
        )

    if state=='direccion_delivery':
        if len(raw) < 5:
            return 'Por favor escribe una dirección un poco más completa y, si puedes, una referencia.'
        data['direccion']=raw
        setsess(phone,'hora',data)
        return '🕐 ¿A qué hora aproximadamente deseas recibir tu pedido? Ejemplo: 1:15 p. m.'

    if state=='hora':
        data['hora']=raw
        setsess(phone,'metodo_pago',data)
        total=total_amount(data.get('modo'),data.get('zona'))
        return (
            f"💰 Total del pedido: *{total}*\n\n"
            "¿Cómo deseas pagar?\n"
            "1️⃣ Yape\n"
            "2️⃣ Efectivo\n\n"
            "Responde 1 o 2."
        )

    if state=='metodo_pago':
        if t not in {'1','2'}:
            return 'Responde *1* para Yape o *2* para efectivo.'

        if t=='1':
            data['pago']='Yape'
            setsess(phone,'yape_comprobante',data)
            return (
                "📱 *PAGO POR YAPE*\n\n"
                f"Yapea a: *{YAPE_NUMBER}*\n"
                f"Titular: *{YAPE_HOLDER}*\n"
                f"Monto: *{total_amount(data.get('modo'),data.get('zona'))}*\n\n"
                "📸 Después de realizar el pago, envía una *captura del comprobante de Yape*.\n"
                "El pedido quedará pendiente de verificación del pago."
            )

        data['pago']='Efectivo'
        setsess(phone,'efectivo_monto',data)
        return (
            "💵 *PAGO EN EFECTIVO*\n\n"
            f"Total: *{total_amount(data.get('modo'),data.get('zona'))}*\n"
            "¿Con cuánto pagarás?\n\n"
            "Escribe el monto, por ejemplo *20*, o escribe *exacto*."
        )

    if state=='yape_comprobante':
        return (
            "📸 Para continuar con Yape, envía una *imagen del comprobante*.\n"
            "No necesitas escribir el código de operación."
        )

    if state=='efectivo_monto':
        total_num=total_numeric(data.get('modo'),data.get('zona'))

        if t in {'exacto','monto exacto','justo'}:
            data['efectivo_entrega']='Monto exacto'
            data['vuelto']='S/ 0.00'
        else:
            try:
                amount=float(raw.replace('s/','').replace(',','.').strip())
                if total_num is not None and amount < total_num:
                    return (
                        f"El total es *{money(total_num)}*. "
                        "Indica un monto igual o mayor, o escribe *exacto*."
                    )
                data['efectivo_entrega']=money(amount)
                if total_num is not None:
                    data['vuelto']=money(amount-total_num)
            except Exception:
                return 'Escribe un monto, por ejemplo *20*, o escribe *exacto*.'

        setsess(phone,'confirmar',data)
        return order_summary(data)
    if state=='confirmar':
        if t=='1':
            oid=new_order(phone,data)
            setsess(phone,'main',{})
            pago_msg = (
                "\n📱 Pago Yape: *comprobante recibido, pendiente de verificación*."
                if data.get('pago')=='Yape'
                else "\n💵 Pago: *efectivo*."
            )
            return (
                f"✅ *Pedido #{oid} recibido*\n"
                "Tu pedido quedó registrado."
                + pago_msg
                + "\n\n📦 Para seguirlo, vuelve al menú y elige *4. Estado de mi pedido*."
                + "\n\nGracias por elegir Punto Verde Express 🌿\nEscribe *0* para volver."
            )
        if t=='2': setsess(phone,'main',{}); return 'Pedido cancelado.\n\n'+MAIN
        return 'Responde *1* para confirmar o *2* para cancelar.'
    if state=='parrilla':
        oid=new_order(phone,{'tipo':'Parrilla del sábado','solicitud':raw}); setsess(phone,'main',{}); p=SATURDAY_GRILL_PRICE or 'por confirmar'
        return f'🔥 *Reserva #{oid} registrada*\nSolicitud: {raw}\nPrecio: {p}\nPendiente de confirmación.\n\nEscribe *0* para volver.'
    setsess(phone,'main',{}); return MAIN


def receive_image(phone, media_ref, source='meta'):
    state,data=sess(phone)
    if state!='yape_comprobante':
        return (
            "📷 Recibí una imagen, pero ahora mismo no estoy esperando un comprobante de Yape.\n"
            "Escribe *0* para volver al menú."
        )

    data['comprobante_yape']=media_ref or 'recibido'
    data['comprobante_source']=source
    data['pago_estado']='Pendiente de verificación'
    setsess(phone,'confirmar',data)
    return (
        "✅ *Comprobante recibido*\n\n"
        "El pago quedó *pendiente de verificación*.\n\n"
        + order_summary(data)
    )

def send_text(to,body):
    if WAIA_API_KEY and WAIA_CONNECTION_ID:
        return requests.post(
            'https://api.waiaconnect.com/v1/messages',
            headers={
                'Authorization':f'Bearer {WAIA_API_KEY}',
                'Idempotency-Key':str(uuid.uuid4()),
                'Content-Type':'application/json'
            },
            json={
                'connectionId':WAIA_CONNECTION_ID,
                'to':str(to),
                'type':'text',
                'text':{'body':body}
            },
            timeout=20
        )
    if not (ACCESS_TOKEN and PHONE_NUMBER_ID and GRAPH_API_VERSION):
        return None
    url=f'https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages'
    headers={'Authorization':f'Bearer {ACCESS_TOKEN}','Content-Type':'application/json'}
    payload={'messaging_product':'whatsapp','to':to,'type':'text','text':{'body':body}}
    return requests.post(url,headers=headers,json=payload,timeout=20)

def waia_signature_ok(raw):
    if WAIA_WEBHOOK_SECRET:
        ts=request.headers.get('X-Connect-Timestamp','')
        sig=request.headers.get('X-Connect-Signature-256','')
        try:
            if abs(time.time()-int(ts)) > 300:
                return False
        except Exception:
            return False
        if not sig.startswith('sha256='):
            return False
        expected=hmac.new(WAIA_WEBHOOK_SECRET.encode(),ts.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected,sig.split('=',1)[1])
    if WAIA_WEBHOOK_TOKEN:
        return hmac.compare_digest(request.headers.get('X-Connect-Token',''),WAIA_WEBHOOK_TOKEN)
    return True

def signature_ok(raw,sig):
    if not APP_SECRET:return True
    if not sig or not sig.startswith('sha256='):return False
    expected=hmac.new(APP_SECRET.encode(),raw,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,sig.split('=',1)[1])

@app.get('/')
def home(): return jsonify({'name':'Punto Verde Express Bot','status':'ok','demo':'/demo','meta_webhook':'/webhook','waia_webhook':'/waia-webhook'})
@app.get('/demo')
def demo(): return render_template_string(DEMO)
@app.post('/demo-message')
def dm():
    p=request.get_json(silent=True) or {}; phone='demo-user'
    if p.get('reset'): setsess(phone,'main',{})
    return jsonify({'reply':reply(phone,str(p.get('text','')))})
@app.post('/demo-image')
def demo_image():
    phone='demo-user'
    f=request.files.get('image')
    if not f:
        return jsonify({'reply':'No recibí ninguna imagen.'}),400
    mimetype=(f.mimetype or '').lower()
    if not mimetype.startswith('image/'):
        return jsonify({'reply':'Envía una imagen del comprobante de Yape.'}),400
    os.makedirs(UPLOAD_DIR,exist_ok=True)
    ext=os.path.splitext(f.filename or '')[1].lower() or '.jpg'
    name=str(uuid.uuid4())+ext
    f.save(os.path.join(UPLOAD_DIR,name))
    return jsonify({'reply':receive_image(phone,name,'demo')})
@app.get('/webhook')
def verify():
    if request.args.get('hub.mode')=='subscribe' and request.args.get('hub.verify_token')==VERIFY_TOKEN:return Response(request.args.get('hub.challenge',''),200)
    return Response('Verification failed',403)
@app.post('/webhook')
def webhook():
    raw=request.get_data()
    if not signature_ok(raw,request.headers.get('X-Hub-Signature-256')): return Response('Invalid signature',401)
    p=request.get_json(silent=True) or {}
    try:
        value=p['entry'][0]['changes'][0]['value']; msgs=value.get('messages',[])
        if msgs:
            m=msgs[0]; sender=m['from']; typ=m.get('type')
            if typ=='image':
                media_id=m.get('image',{}).get('id','')
                send_text(sender,receive_image(sender,media_id,'meta'))
            else:
                if typ=='text': incoming=m['text']['body']
                elif typ=='button': incoming=m['button'].get('text','')
                elif typ=='interactive': incoming=m['interactive'].get('button_reply',{}).get('id') or m['interactive'].get('list_reply',{}).get('id','')
                else: incoming='hola'
                send_text(sender,reply(sender,incoming))
    except Exception as e: app.logger.exception(e)
    return Response('EVENT_RECEIVED',200)
@app.post('/waia-webhook')
def waia_webhook():
    raw=request.get_data()
    if not waia_signature_ok(raw):
        return Response('Invalid WAIA signature',401)
    delivery_id=request.headers.get('X-Connect-Delivery-Id','')
    if event_seen(delivery_id):
        return Response('OK',200)
    p=request.get_json(silent=True) or {}
    event_type=request.headers.get('X-Connect-Event') or p.get('type','')
    if event_type=='webhook.test':
        return jsonify({'ok':True})
    if event_type!='message.received':
        return Response('OK',200)
    data=p.get('data') or {}
    m=data.get('message') or {}
    sender=str(m.get('from',''))
    typ=m.get('type','')
    if not sender:
        return Response('OK',200)
    try:
        if typ=='image':
            answer=receive_image(sender,(m.get('image') or {}).get('id',''),'waia')
        elif typ=='text':
            answer=reply(sender,(m.get('text') or {}).get('body',''))
        else:
            answer='Por ahora puedo atender texto y comprobantes en imagen. Escribe *hola* para comenzar.'
        send_text(sender,answer)
    except Exception as e:
        app.logger.exception(e)
    return Response('OK',200)

@app.get('/admin')
def admin_panel():
    if request.args.get('key') != ADMIN_KEY:
        return Response('Acceso no autorizado',403)

    q=(request.args.get('q') or '').strip().lower()
    with db() as c:
        rows=c.execute('SELECT id,phone,details,status,created_at,updated_at FROM orders ORDER BY id DESC LIMIT 150').fetchall()

    total=len(rows)
    nuevos=sum(1 for r in rows if r[3]=='Pedido recibido')
    yapes=0
    cards=[]
    allowed=['Pedido recibido','Confirmado','En preparación','Listo para recojo','En camino','Entregado','Cancelado']
    pay_allowed=['Pendiente de verificación','Pago verificado','Pago rechazado','Pago al entregar','Pagado']

    for oid,phone,details_json,status,created_at,updated_at in rows:
        try:
            d=json.loads(details_json or '{}')
        except Exception:
            d={}
        pay_status=order_payment_status(d)
        if d.get('pago')=='Yape' and pay_status=='Pendiente de verificación':
            yapes+=1
        blob=' '.join([str(oid),str(phone),d.get('cliente',''),d.get('entrada',''),d.get('segundo',''),d.get('direccion',''),status,pay_status]).lower()
        if q and q not in blob:
            continue

        pedido=' + '.join(x for x in [d.get('entrada'),d.get('segundo')] if x) or d.get('tipo','Pedido')
        entrega=(f"Delivery · {d.get('zona','')} · {d.get('direccion','')}" if d.get('modo')=='Delivery' else d.get('modo','Recojo'))
        total_order=(total_amount(d.get('modo'),d.get('zona')) if d.get('entrada') else (SATURDAY_GRILL_PRICE or 'por confirmar'))
        opts=''.join('<option value="'+html.escape(s)+'"'+(' selected' if s==status else '')+'>'+html.escape(s)+'</option>' for s in allowed)
        popts=''.join('<option value="'+html.escape(s)+'"'+(' selected' if s==pay_status else '')+'>'+html.escape(s)+'</option>' for s in pay_allowed)
        receipt=''
        if d.get('pago')=='Yape' and d.get('comprobante_yape'):
            receipt=f'<a class="receipt" target="_blank" href="/admin/order/{oid}/receipt?key={html.escape(ADMIN_KEY)}">📸 Ver comprobante</a>'
        cls='card new' if status=='Pedido recibido' else 'card'
        cards.append(
            f'<div class="{cls}">'
            f'<div class="head"><h3>Pedido #{oid}</h3><span>{html.escape(status)}</span></div>'
            f'<div class="grid"><div><b>👤 Cliente</b><br>{html.escape(d.get("cliente","Sin nombre"))}</div>'
            f'<div><b>🍽️ Pedido</b><br>{html.escape(pedido)}</div>'
            f'<div><b>📍 Entrega</b><br>{html.escape(entrega)}</div>'
            f'<div><b>💰 Total</b><br>{html.escape(str(total_order))}</div>'
            f'<div><b>💳 Pago</b><br>{html.escape(d.get("pago","Sin registrar"))}</div>'
            f'<div><b>🔎 Estado de pago</b><br>{html.escape(pay_status)}</div></div>'
            f'{receipt}'
            f'<form class="row" method="post" action="/admin/order/{oid}?key={html.escape(ADMIN_KEY)}"><select name="status">{opts}</select><button>Actualizar pedido</button></form>'
            f'<form class="row" method="post" action="/admin/order/{oid}/payment?key={html.escape(ADMIN_KEY)}"><select name="payment_status">{popts}</select><button class="dark">Actualizar pago</button></form>'
            '</div>'
        )

    page=(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Panel Punto Verde</title>'
        '<style>*{box-sizing:border-box}body{font-family:Arial;background:#f4f7f5;margin:0;color:#23322d}.w{max-width:900px;margin:auto;padding:16px}h1{color:#075e54}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.stat,.card,.search{background:white;border-radius:14px;padding:14px;box-shadow:0 2px 12px #dfe7e2}.stat b{display:block;font-size:26px;color:#075e54}.search{margin:12px 0;display:flex;gap:8px}.search input{flex:1}.card{margin:12px 0;border-left:5px solid #dbe5df}.card.new{border-left-color:#ff9800;background:#fffdf8}.head{display:flex;justify-content:space-between;align-items:center}.head h3{margin:0;color:#075e54}.head span{background:#eaf6f0;padding:6px 9px;border-radius:999px;font-size:12px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0}.row{display:flex;gap:8px;margin-top:8px}.row select{flex:1}input,select,button{padding:11px;border:1px solid #ccd8d1;border-radius:9px}button{background:#00a884;color:white;border:0;font-weight:bold}.dark{background:#075e54}.receipt{display:inline-block;background:#54656f;color:white;text-decoration:none;padding:9px 12px;border-radius:9px}@media(max-width:650px){.stats,.grid{grid-template-columns:1fr}.row,.search{flex-direction:column}}</style>'
        f'<div class="w"><h1>🌿 Punto Verde Express</h1><p>Panel de pedidos y verificación de pagos</p><div class="stats"><div class="stat"><b>{total}</b>Pedidos</div><div class="stat"><b>{nuevos}</b>Nuevos</div><div class="stat"><b>{yapes}</b>Yapes por verificar</div></div>'
        f'<form class="search" method="get"><input type="hidden" name="key" value="{html.escape(ADMIN_KEY)}"><input name="q" value="{html.escape(q)}" placeholder="Buscar pedido, cliente o dirección"><button>Buscar</button></form>'
        + (''.join(cards) if cards else '<div class="card">No se encontraron pedidos.</div>') + '</div>'
    )
    return page

@app.post('/admin/order/<int:order_id>')
def admin_update_order(order_id):
    if request.args.get('key') != ADMIN_KEY:
        return Response('Acceso no autorizado',403)
    allowed=['Pedido recibido','Confirmado','En preparación','Listo para recojo','En camino','Entregado','Cancelado']
    status=request.form.get('status','')
    if status not in allowed:
        return Response('Estado inválido',400)
    update_order_status(order_id,status)
    order=get_order(order_id)
    if order:
        send_text(order[1],f'📦 Tu pedido #{order_id} ahora está: *{status}*.\nEscribe *4* para revisar el seguimiento.')
    return Response('<meta http-equiv="refresh" content="0;url=/admin?key='+ADMIN_KEY+'">',200,mimetype='text/html')

@app.post('/admin/order/<int:order_id>/payment')
def admin_update_payment(order_id):
    if request.args.get('key') != ADMIN_KEY:
        return Response('Acceso no autorizado',403)
    allowed=['Pendiente de verificación','Pago verificado','Pago rechazado','Pago al entregar','Pagado']
    payment_status=request.form.get('payment_status','')
    if payment_status not in allowed:
        return Response('Estado de pago inválido',400)
    result=update_payment_status(order_id,payment_status)
    if result:
        phone,details,new_status=result
        if payment_status=='Pago verificado':
            send_text(phone,f'✅ El pago de tu pedido #{order_id} fue *verificado*.\nEstado del pedido: *{new_status}*.')
        elif payment_status=='Pago rechazado':
            send_text(phone,f'⚠️ No pudimos verificar el pago de tu pedido #{order_id}. Comunícate con nosotros o envía un comprobante válido.')
    return Response('<meta http-equiv="refresh" content="0;url=/admin?key='+ADMIN_KEY+'">',200,mimetype='text/html')

@app.get('/admin/order/<int:order_id>/receipt')
def admin_receipt(order_id):
    if request.args.get('key') != ADMIN_KEY:
        return Response('Acceso no autorizado',403)
    order=get_order(order_id)
    if not order:
        return Response('Pedido no encontrado',404)
    try:
        d=json.loads(order[2] or '{}')
    except Exception:
        d={}
    media_id=d.get('comprobante_yape')
    source=d.get('comprobante_source')
    if not media_id:
        return Response('Este pedido no tiene comprobante',404)
    try:
        if source=='demo':
            path=os.path.join(UPLOAD_DIR,os.path.basename(media_id))
            if not os.path.isfile(path):
                return Response('Comprobante no disponible',404)
            with open(path,'rb') as fh:
                content=fh.read()
            mime='image/png' if path.lower().endswith('.png') else 'image/jpeg'
            return Response(content,200,content_type=mime)
        if source=='waia' and WAIA_API_KEY:
            r=requests.get(f'https://api.waiaconnect.com/v1/media/{media_id}',headers={'Authorization':f'Bearer {WAIA_API_KEY}'},timeout=20)
            if not r.ok:
                return Response('No se pudo descargar el comprobante desde WAIA',502)
            return Response(r.content,200,content_type=r.headers.get('Content-Type','image/jpeg'))
        if source=='meta' and ACCESS_TOKEN and GRAPH_API_VERSION:
            info=requests.get(f'https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}',headers={'Authorization':f'Bearer {ACCESS_TOKEN}'},timeout=20)
            if not info.ok:
                return Response('No se pudo consultar el comprobante en Meta',502)
            url=(info.json() or {}).get('url')
            media=requests.get(url,headers={'Authorization':f'Bearer {ACCESS_TOKEN}'},timeout=20)
            return Response(media.content,media.status_code,content_type=media.headers.get('Content-Type','image/jpeg'))
    except Exception as e:
        app.logger.exception(e)
        return Response('Error al abrir el comprobante',500)
    return Response('Proveedor no configurado',400)

@app.get('/health')
def health(): return jsonify({'status':'ok'})

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')),debug=os.getenv('FLASK_DEBUG')=='1')
