import os, json, sqlite3, hmac, hashlib
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
DB_PATH=os.getenv('DB_PATH','punto_verde.db')
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

MAIN=("🌿 *PUNTO VERDE EXPRESS* 🌿\nMenús & Parrillas\n\n¡Hola! 👋 ¿Qué deseas hacer?\n"
      "1️⃣ Ver menú de hoy\n2️⃣ Hacer un pedido\n3️⃣ Parrillas del sábado\n4️⃣ Estado de mi pedido\n5️⃣ Hablar con una persona\n\nResponde con el número de una opción.")

DEMO='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Punto Verde Express</title><style>body{font-family:Arial;background:#efeae2;margin:0}.w{max-width:430px;height:760px;margin:18px auto;background:white;display:flex;flex-direction:column;border-radius:18px;overflow:hidden;box-shadow:0 5px 25px #999}.h{background:#075e54;color:white;padding:16px;font-weight:bold}.c{flex:1;padding:14px;overflow:auto;background:#efeae2}.m{white-space:pre-wrap;padding:9px 11px;border-radius:10px;margin:7px 0;max-width:82%;background:white}.me{margin-left:auto;background:#d9fdd3}.b{display:flex;gap:8px;padding:10px;background:#f0f2f5}.b input{flex:1;border:0;border-radius:20px;padding:12px}.b button{border:0;border-radius:20px;background:#00a884;color:white;padding:0 16px}</style><div class="w"><div class="h">Punto Verde Express<br><small>Prototipo del bot</small></div><div id="c" class="c"></div><div class="b"><input id="i" placeholder="Escribe 1, 2, 3..."><button onclick="s()">Enviar</button></div></div><script>const c=document.getElementById('c'),i=document.getElementById('i');function a(t,k){let d=document.createElement('div');d.className='m '+k;d.textContent=t;c.appendChild(d);c.scrollTop=c.scrollHeight}async function s(){let t=i.value.trim();if(!t)return;a(t,'me');i.value='';let r=await fetch('/demo-message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});let j=await r.json();a(j.reply,'')}i.onkeydown=e=>{if(e.key==='Enter')s()};fetch('/demo-message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'hola',reset:true})}).then(r=>r.json()).then(j=>a(j.reply,''));</script>'''

def db():
    conn=sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS sessions(phone TEXT PRIMARY KEY,state TEXT,data TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,phone TEXT,details TEXT,status TEXT,created_at TEXT)')
    cols=[r[1] for r in conn.execute('PRAGMA table_info(orders)').fetchall()]
    if 'updated_at' not in cols:
        conn.execute('ALTER TABLE orders ADD COLUMN updated_at TEXT')
        conn.execute('UPDATE orders SET updated_at=created_at WHERE updated_at IS NULL')
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

def new_order(phone,details):
    now=datetime.now(TZ).isoformat()
    with db() as c:
        q=c.execute(
            'INSERT INTO orders(phone,details,status,created_at,updated_at) VALUES(?,?,?,?,?)',
            (phone,json.dumps(details,ensure_ascii=False),'Pedido recibido',now,now)
        )
        c.commit()
        return q.lastrowid

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
        if status=='Cancelado':
            mark='○'
        elif i < idx:
            mark='✅'
        elif i == idx:
            mark='➡️'
        else:
            mark='○'
        lines.append(f'{mark} {icon} {name}')
    if status=='Cancelado':
        lines.append('❌ Pedido cancelado')
    if details.get('modo')=='Delivery':
        extra=f"\n📍 {details.get('zona','')} — {details.get('direccion','')}"
    else:
        extra='\n📍 Modalidad: Recojo'
    return (
        f"📦 *SEGUIMIENTO DEL PEDIDO #{oid}*\n\n"
        + "\n".join(lines)
        + f"\n\nEstado actual: *{status}*"
        + extra
        + "\n\nEscribe *0* para volver al menú."
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
        if t not in {'1','2','3'}: return 'Responde solo *1, 2 o 3* para elegir el segundo.'
        m=MENUS[data['day']]; data['segundo']=m['segundos'][int(t)-1]; setsess(phone,'modo',data)
        return f"✅ Segundo: *{data['segundo']}*\n\n¿Cómo deseas recibirlo?\n1️⃣ Recojo\n2️⃣ Delivery"
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
        setsess(phone,'confirmar',data)
        zone = data.get('zona')
        delivery_value = money(delivery_fee(zone)) if data['modo']=='Delivery' else 'S/ 0.00'
        total = total_amount(data['modo'], zone)
        extra = ''
        if data['modo']=='Delivery':
            extra = f"\nZona: {data.get('zona','')}\nDirección: {data.get('direccion','')}"
        return (
            f"🧾 *RESUMEN DEL PEDIDO*\n\n"
            f"Entrada: {data['entrada']}\n"
            f"Segundo: {data['segundo']}\n"
            f"Modalidad: {data['modo']}"
            f"{extra}\n"
            f"Hora: {data['hora']}\n\n"
            f"💵 Precio: {money(MENU_PRICE)}\n"
            f"🚚 Delivery: {delivery_value}\n"
            f"💰 *TOTAL: {total}*\n\n"
            "1️⃣ Sí, confirmar\n"
            "2️⃣ No, cancelar"
        )
    if state=='confirmar':
        if t=='1':
            oid=new_order(phone,data); setsess(phone,'main',{}); return f'✅ *Pedido #{oid} recibido*\nTu pedido quedó registrado.\n\n📦 Para seguirlo, vuelve al menú y elige *4. Estado de mi pedido*.\n\nGracias por elegir Punto Verde Express 🌿\nEscribe *0* para volver.'
        if t=='2': setsess(phone,'main',{}); return 'Pedido cancelado.\n\n'+MAIN
        return 'Responde *1* para confirmar o *2* para cancelar.'
    if state=='parrilla':
        oid=new_order(phone,{'tipo':'Parrilla del sábado','solicitud':raw}); setsess(phone,'main',{}); p=SATURDAY_GRILL_PRICE or 'por confirmar'
        return f'🔥 *Reserva #{oid} registrada*\nSolicitud: {raw}\nPrecio: {p}\nPendiente de confirmación.\n\nEscribe *0* para volver.'
    setsess(phone,'main',{}); return MAIN

def send_text(to,body):
    if not (ACCESS_TOKEN and PHONE_NUMBER_ID and GRAPH_API_VERSION): return None
    url=f'https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages'
    headers={'Authorization':f'Bearer {ACCESS_TOKEN}','Content-Type':'application/json'}
    payload={'messaging_product':'whatsapp','to':to,'type':'text','text':{'body':body}}
    return requests.post(url,headers=headers,json=payload,timeout=20)

def signature_ok(raw,sig):
    if not APP_SECRET:return True
    if not sig or not sig.startswith('sha256='):return False
    expected=hmac.new(APP_SECRET.encode(),raw,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,sig.split('=',1)[1])

@app.get('/')
def home(): return jsonify({'name':'Punto Verde Express Bot','status':'ok','demo':'/demo','webhook':'/webhook'})
@app.get('/demo')
def demo(): return render_template_string(DEMO)
@app.post('/demo-message')
def dm():
    p=request.get_json(silent=True) or {}; phone='demo-user'
    if p.get('reset'): setsess(phone,'main',{})
    return jsonify({'reply':reply(phone,str(p.get('text','')))})
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
            if typ=='text': incoming=m['text']['body']
            elif typ=='button': incoming=m['button'].get('text','')
            elif typ=='interactive': incoming=m['interactive'].get('button_reply',{}).get('id') or m['interactive'].get('list_reply',{}).get('id','')
            else: incoming='hola'
            send_text(sender,reply(sender,incoming))
    except Exception as e: app.logger.exception(e)
    return Response('EVENT_RECEIVED',200)
@app.get('/admin')
def admin_panel():
    if request.args.get('key') != ADMIN_KEY:
        return Response('Acceso no autorizado',403)
    with db() as c:
        rows=c.execute(
            'SELECT id,phone,details,status,created_at,updated_at FROM orders ORDER BY id DESC LIMIT 50'
        ).fetchall()

    allowed=['Pedido recibido','Confirmado','En preparación','Listo para recojo','En camino','Entregado','Cancelado']
    cards=[]
    for oid,phone,details_json,status,created_at,updated_at in rows:
        try:
            d=json.loads(details_json or '{}')
        except Exception:
            d={}
        if d.get('entrada') or d.get('segundo'):
            pedido=f"{d.get('entrada','')} + {d.get('segundo','')}"
        else:
            pedido=d.get('tipo','Pedido')
        if d.get('modo')=='Delivery':
            modalidad=f"{d.get('zona','')} — {d.get('direccion','')}"
        else:
            modalidad=d.get('modo','Recojo')
        opts=''.join(
            '<option value="'+s+'"'+(' selected' if s==status else '')+'>'+s+'</option>'
            for s in allowed
        )
        card=(
            '<div class="card">'
            f'<h3>Pedido #{oid}</h3>'
            f'<div><b>Pedido:</b> {pedido}</div>'
            f'<div><b>Modalidad:</b> {modalidad}</div>'
            f'<div><b>Estado:</b> {status}</div>'
            f'<form method="post" action="/admin/order/{oid}?key={ADMIN_KEY}">'
            f'<select name="status">{opts}</select>'
            '<button type="submit">Actualizar estado</button>'
            '</form></div>'
        )
        cards.append(card)

    html=(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Panel Punto Verde</title>'
        '<style>'
        'body{font-family:Arial;background:#f3f5f4;margin:0;padding:18px}'
        '.wrap{max-width:720px;margin:auto}'
        'h1{color:#075e54}'
        '.card{background:white;padding:16px;margin:12px 0;border-radius:14px;box-shadow:0 2px 12px #ddd}'
        'select,button{padding:10px;margin-top:10px;border-radius:9px}'
        'button{background:#00a884;color:white;border:0}'
        '</style>'
        '<div class="wrap">'
        '<h1>🌿 Punto Verde Express — Pedidos</h1>'
        '<p>Desde aquí puedes cambiar el estado. El cliente lo verá en la opción 4.</p>'
        + (''.join(cards) if cards else '<p>No hay pedidos todavía.</p>')
        + '</div>'
    )
    return html

@app.post('/admin/order/<int:order_id>')
def admin_update_order(order_id):
    if request.args.get('key') != ADMIN_KEY:
        return Response('Acceso no autorizado',403)
    allowed=['Pedido recibido','Confirmado','En preparación','Listo para recojo','En camino','Entregado','Cancelado']
    status=request.form.get('status','')
    if status not in allowed:
        return Response('Estado inválido',400)
    update_order_status(order_id,status)
    return Response(
        '<meta http-equiv="refresh" content="0;url=/admin?key='+ADMIN_KEY+'">',
        200,
        mimetype='text/html'
    )

@app.get('/health')
def health(): return jsonify({'status':'ok'})

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')),debug=os.getenv('FLASK_DEBUG')=='1')
