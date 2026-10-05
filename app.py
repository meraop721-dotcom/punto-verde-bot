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
0:{'dia':'Lunes','entradas':['Sopa de pollo','Papa a la huancaína','Causa de pollo'],'segundos':['Arroz con pollo','Ají de gallina','Tallarines rojos con pollo']},
1:{'dia':'Martes','entradas':['Aguadito de pollo','Papa rellena','Ensalada rusa'],'segundos':['Lomo saltado','Milanesa de pollo','Cau cau']},
2:{'dia':'Miércoles','entradas':['Sopa de verduras','Ocopa','Tamal criollo'],'segundos':['Pescado frito','Arroz chaufa de pollo','Seco de pollo']},
3:{'dia':'Jueves','entradas':['Caldo de gallina','Causa de pollo','Papa a la huancaína'],'segundos':['Arroz con pato','Pollo al horno','Tallarines verdes con pollo']},
4:{'dia':'Viernes','entradas':['Chilcano de pescado','Causa de atún','Papa rellena'],'segundos':['Seco de cabrito','Lomo saltado','Pescado sudado']},
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
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#075e54">
<title>Punto Verde Express · Demo</title>
<style>
:root{
  --green:#075e54;
  --green2:#0b7d66;
  --accent:#16a36f;
  --lime:#dff6e8;
  --paper:#ffffff;
  --bg:#eef5f1;
  --ink:#173129;
  --muted:#6f817a;
  --line:#dce8e1;
  --orange:#f59e0b;
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:var(--ink);
  background:
    radial-gradient(circle at 10% 10%,#dff3e9 0,transparent 26%),
    radial-gradient(circle at 90% 85%,#fdeed5 0,transparent 24%),
    #edf3f0;
}
.shell{
  min-height:100%;
  display:flex;
  align-items:center;
  justify-content:center;
  padding:20px;
}
.phone{
  width:min(100%,460px);
  height:min(850px,calc(100vh - 40px));
  background:#fff;
  border-radius:28px;
  overflow:hidden;
  box-shadow:0 22px 70px rgba(18,60,47,.22);
  display:flex;
  flex-direction:column;
  border:1px solid rgba(255,255,255,.8);
}
.top{
  background:linear-gradient(135deg,#064e45,#08745f);
  color:#fff;
  padding:15px 16px 13px;
  box-shadow:0 4px 18px rgba(0,0,0,.13);
  position:relative;
  z-index:3;
}
.brandrow{display:flex;align-items:center;gap:12px}
.logo{
  width:48px;height:48px;border-radius:50%;
  background:#fff;
  display:grid;place-items:center;
  box-shadow:0 4px 14px rgba(0,0,0,.15);
  flex:0 0 auto;
}
.logo svg{width:31px;height:31px}
.brand{min-width:0;flex:1}
.brand h1{font-size:17px;line-height:1.1;margin:0;font-weight:800;letter-spacing:.1px}
.sub{display:flex;align-items:center;gap:6px;font-size:12px;opacity:.9;margin-top:5px}
.dot{width:7px;height:7px;background:#9ff2c5;border-radius:50%;box-shadow:0 0 0 3px rgba(159,242,197,.14)}
.reset{
  border:1px solid rgba(255,255,255,.24);
  color:#fff;background:rgba(255,255,255,.11);
  border-radius:12px;padding:9px 11px;font-size:12px;font-weight:700;cursor:pointer
}
.info{
  display:flex;gap:8px;overflow:auto;
  padding:9px 12px;background:#fff;border-bottom:1px solid var(--line);
  scrollbar-width:none
}
.info::-webkit-scrollbar{display:none}
.chip{
  white-space:nowrap;border:1px solid #dbeae3;background:#f7fbf9;color:#33584c;
  border-radius:999px;padding:7px 10px;font-size:11px;font-weight:700
}
.chat{
  flex:1;
  min-height:0;
  overflow:auto;
  padding:16px 13px 18px;
  background-color:#eef3f0;
  background-image:radial-gradient(#d7e5de 1px,transparent 1px);
  background-size:18px 18px;
  scroll-behavior:smooth;
}
.msgrow{display:flex;align-items:flex-end;gap:7px;margin:9px 0}
.msgrow.me{justify-content:flex-end}
.botavatar{
  width:27px;height:27px;border-radius:50%;background:#fff;border:1px solid #d8e5df;
  display:grid;place-items:center;font-size:14px;box-shadow:0 2px 7px rgba(0,0,0,.08);flex:0 0 auto
}
.bubble{
  max-width:82%;
  background:#fff;
  border-radius:15px 15px 15px 5px;
  padding:10px 12px 7px;
  box-shadow:0 1px 2px rgba(0,0,0,.08);
  font-size:14px;line-height:1.43;
  word-break:break-word;
}
.me .bubble{
  background:#d9fdd3;
  border-radius:15px 15px 5px 15px
}
.meta{margin-top:5px;color:#80918a;font-size:9.5px;text-align:right}
.typing{
  display:none;align-items:center;gap:5px;background:#fff;border-radius:14px 14px 14px 5px;
  padding:11px 13px;width:max-content;box-shadow:0 1px 2px rgba(0,0,0,.08);margin:8px 0 8px 34px
}
.typing span{width:6px;height:6px;border-radius:50%;background:#8aa198;animation:b 1.1s infinite}
.typing span:nth-child(2){animation-delay:.15s}.typing span:nth-child(3){animation-delay:.3s}
@keyframes b{0%,70%,100%{transform:translateY(0);opacity:.4}35%{transform:translateY(-4px);opacity:1}}
.quick{
  display:flex;gap:7px;overflow:auto;padding:9px 10px;background:#f8fbf9;border-top:1px solid var(--line);
  scrollbar-width:none
}
.quick::-webkit-scrollbar{display:none}
.quick button{
  white-space:nowrap;border:1px solid #cfe3d9;background:#fff;color:#17634f;border-radius:999px;
  padding:8px 11px;font-size:12px;font-weight:800;cursor:pointer
}
.composer{
  display:flex;align-items:center;gap:8px;padding:10px;
  background:#fff;border-top:1px solid var(--line);
  padding-bottom:max(10px,env(safe-area-inset-bottom));
  position:relative;z-index:10;flex:0 0 auto
}
.textwrap{
  flex:1;display:flex;align-items:center;background:#f3f6f5;border:1px solid #e2ebe6;border-radius:22px;padding:0 5px 0 12px
}
.textwrap input[type=text]{
  flex:1;border:0;outline:0;background:transparent;padding:12px 5px;
  font-size:16px;min-width:0;color:#1e352d;display:block;
  -webkit-user-select:text;user-select:text;touch-action:manipulation
}
.camera{
  width:38px;height:38px;border-radius:50%;display:grid;place-items:center;cursor:pointer;
  color:#49665c;font-size:17px
}
#f{display:none}
.send{
  width:42px;height:42px;border-radius:50%;border:0;background:linear-gradient(135deg,#15a06c,#08745f);
  color:#fff;display:grid;place-items:center;cursor:pointer;box-shadow:0 5px 13px rgba(8,116,95,.24);font-size:17px
}
.badge{
  position:absolute;right:15px;bottom:-10px;background:#fff;color:#0b6d59;padding:5px 9px;border-radius:999px;
  font-size:10px;font-weight:800;box-shadow:0 3px 11px rgba(0,0,0,.12)
}
@media(max-width:520px){
  .shell{padding:0}
  .phone{width:100%;height:100vh;border-radius:0}
}
</style>
</head>
<body>
<div class="shell">
  <main class="phone">
    <header class="top">
      <div class="brandrow">
        <div class="logo" aria-label="Logo Punto Verde Express">
          <svg viewBox="0 0 64 64" role="img" aria-hidden="true">
            <path d="M32 54C20 48 13 39 13 28c0-8 5-15 13-18 2 8 6 13 12 17-2-8 0-15 7-21 6 5 9 12 8 20-1 15-10 24-21 28Z" fill="#13a16d"/>
            <path d="M30 49c1-12 6-22 16-30" fill="none" stroke="#075e54" stroke-width="4" stroke-linecap="round"/>
            <path d="M25 37c7 0 12 2 16 7" fill="none" stroke="#f3a712" stroke-width="4" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="brand">
          <h1>Punto Verde Express</h1>
          <div class="sub"><span class="dot"></span> Prototipo funcional · En línea</div>
        </div>
        <button class="reset" onclick="resetChat()">↻ Reiniciar</button>
      </div>
      <div class="badge">Menús & Parrillas</div>
    </header>

    <section class="info">
      <span class="chip">🍽️ Menú referencial S/ 12</span>
      <span class="chip">🛵 Delivery Guadalupe / Chepén</span>
      <span class="chip">💳 Yape o efectivo</span>
      <span class="chip">📦 Seguimiento</span>
    </section>

    <section id="c" class="chat" aria-live="polite"></section>
    <div id="typing" class="typing"><span></span><span></span><span></span></div>

    <section class="quick">
      <button onclick="quick('1')">🍽️ Ver menú</button>
      <button onclick="quick('2')">🛒 Hacer pedido</button>
      <button onclick="quick('4')">📦 Mi pedido</button>
      <button onclick="quick('5')">👤 Ayuda</button>
    </section>

    <footer class="composer" id="composer">
      <div class="textwrap">
        <label class="camera" for="f" title="Enviar comprobante">📷</label>
        <input id="f" type="file" accept="image/*" onchange="img()">
        <input id="i" type="text" autocomplete="off" placeholder="Escribe un mensaje...">
      </div>
      <button class="send" onclick="s()" title="Enviar">➤</button>
    </footer>
  </main>
</div>

<script>
const c=document.getElementById('c');
const i=document.getElementById('i');
const f=document.getElementById('f');
const typing=document.getElementById('typing');

function esc(t){
  return String(t).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))
}
function fmt(t){
  let x=esc(t);
  const parts=x.split('*');
  let out='';
  for(let n=0;n<parts.length;n++){
    out += (n%2===1 ? '<strong>'+parts[n]+'</strong>' : parts[n]);
  }
  return out.split(String.fromCharCode(10)).join('<br>');
}
function now(){
  return new Date().toLocaleTimeString('es-PE',{hour:'2-digit',minute:'2-digit'})
}
function add(t,who){
  const row=document.createElement('div');
  row.className='msgrow'+(who==='me'?' me':'');
  if(who!=='me'){
    const av=document.createElement('div');
    av.className='botavatar';
    av.textContent='🌿';
    row.appendChild(av);
  }
  const b=document.createElement('div');
  b.className='bubble';
  b.innerHTML=fmt(t)+'<div class="meta">'+now()+(who==='me'?' ✓✓':'')+'</div>';
  row.appendChild(b);
  c.appendChild(row);
  c.scrollTop=c.scrollHeight
}
function showTyping(v){
  typing.style.display=v?'flex':'none';
  if(v) c.scrollTop=c.scrollHeight
}
async function sendText(t){
  t=String(t||'').trim();
  if(!t)return;
  add(t,'me');
  showTyping(true);
  try{
    const r=await fetch('/demo-message',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:t})
    });
    const j=await r.json();
    await new Promise(r=>setTimeout(r,350));
    showTyping(false);
    add(j.reply,'bot')
  }catch(e){
    showTyping(false);
    add('No pude responder en este momento. Intenta nuevamente.','bot')
  }
}
async function s(){
  const t=i.value;
  i.value='';
  await sendText(t);
  i.focus()
}
function quick(v){sendText(v)}
async function img(){
  if(!f.files.length)return;
  add('📷 Comprobante de Yape enviado','me');
  showTyping(true);
  const fd=new FormData();
  fd.append('image',f.files[0]);
  try{
    const r=await fetch('/demo-image',{method:'POST',body:fd});
    const j=await r.json();
    await new Promise(r=>setTimeout(r,450));
    showTyping(false);
    add(j.reply,'bot')
  }catch(e){
    showTyping(false);
    add('No pude cargar la imagen. Intenta otra vez.','bot')
  }
  f.value=''
}
async function resetChat(){
  c.innerHTML='';
  showTyping(true);
  const r=await fetch('/demo-message',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({text:'hola',reset:true})
  });
  const j=await r.json();
  setTimeout(()=>{showTyping(false);add(j.reply,'bot')},300)
}
document.querySelector('.textwrap').addEventListener('click',function(e){
  if(e.target!==f){ i.focus(); }
});
i.addEventListener('keydown',function(e){
  if(e.key==='Enter'){ e.preventDefault(); s(); }
});
resetChat();
</script>
</body>
</html>'''

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
        return (
            '🔥 *ESPECIAL DE SÁBADO: PARRILLAS*\n\n'
            '1. Pollo a la parrilla\n'
            '2. Parrilla familiar\n'
            '3. Chorizo + pollo + carne\n\n'
            f'Precio: {p}\n\n'
            'Escribe *RESERVAR* para dejar una reserva o *0* para volver.'
        )
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
        rows=c.execute(
            'SELECT id,phone,details,status,created_at,updated_at FROM orders ORDER BY id DESC LIMIT 150'
        ).fetchall()

    total=len(rows)
    nuevos=sum(1 for r in rows if r[3]=='Pedido recibido')
    en_ruta=sum(1 for r in rows if r[3]=='En camino')
    entregados=sum(1 for r in rows if r[3]=='Entregado')
    yapes=0
    cards=[]

    allowed=['Pedido recibido','Confirmado','En preparación','Listo para recojo','En camino','Entregado','Cancelado']
    pay_allowed=['Pendiente de verificación','Pago verificado','Pago rechazado','Pago al entregar','Pagado']

    def status_class(value):
        return {
            'Pedido recibido':'st-new',
            'Confirmado':'st-ok',
            'En preparación':'st-prep',
            'Listo para recojo':'st-ready',
            'En camino':'st-route',
            'Entregado':'st-done',
            'Cancelado':'st-cancel'
        }.get(value,'st-new')

    def pay_class(value):
        return {
            'Pendiente de verificación':'pay-wait',
            'Pago verificado':'pay-ok',
            'Pago rechazado':'pay-bad',
            'Pago al entregar':'pay-cash',
            'Pagado':'pay-ok'
        }.get(value,'pay-wait')

    def pretty_time(value):
        if not value:
            return 'Sin fecha'
        try:
            dt=datetime.fromisoformat(value)
            return dt.astimezone(TZ).strftime('%d/%m/%Y · %I:%M %p')
        except Exception:
            return str(value)

    for oid,phone,details_json,status,created_at,updated_at in rows:
        try:
            d=json.loads(details_json or '{}')
        except Exception:
            d={}

        pay_status=order_payment_status(d)
        if d.get('pago')=='Yape' and pay_status=='Pendiente de verificación':
            yapes+=1

        blob=' '.join([
            str(oid),str(phone),d.get('cliente',''),d.get('entrada',''),
            d.get('segundo',''),d.get('direccion',''),status,pay_status
        ]).lower()
        if q and q not in blob:
            continue

        pedido=' + '.join(x for x in [d.get('entrada'),d.get('segundo')] if x) or d.get('tipo','Pedido')
        if d.get('modo')=='Delivery':
            entrega=f"{d.get('zona','')} · {d.get('direccion','')}"
            delivery_badge='🛵 Delivery'
        else:
            entrega=d.get('modo','Recojo')
            delivery_badge='🥡 Recojo'

        total_order=(
            total_amount(d.get('modo'),d.get('zona'))
            if d.get('entrada')
            else (SATURDAY_GRILL_PRICE or 'por confirmar')
        )

        opts=''.join(
            '<option value="'+html.escape(s)+'"'+(' selected' if s==status else '')+'>'+html.escape(s)+'</option>'
            for s in allowed
        )
        popts=''.join(
            '<option value="'+html.escape(s)+'"'+(' selected' if s==pay_status else '')+'>'+html.escape(s)+'</option>'
            for s in pay_allowed
        )

        receipt=''
        if d.get('pago')=='Yape' and d.get('comprobante_yape'):
            receipt=(
                f'<a class="receipt" target="_blank" '
                f'href="/admin/order/{oid}/receipt?key={html.escape(ADMIN_KEY)}">'
                '📸 Abrir comprobante</a>'
            )

        is_new=' new' if status=='Pedido recibido' else ''
        payment_icon='📱' if d.get('pago')=='Yape' else '💵'
        client=html.escape(d.get('cliente','Sin nombre'))
        pedido_safe=html.escape(pedido)
        entrega_safe=html.escape(entrega)
        total_safe=html.escape(str(total_order))
        metodo=html.escape(d.get('pago','Sin registrar'))
        status_safe=html.escape(status)
        pay_safe=html.escape(pay_status)
        hora=html.escape(d.get('hora','Sin horario'))
        updated=html.escape(pretty_time(updated_at or created_at))

        cards.append(
            f'''
            <article class="order-card{is_new}">
              <div class="order-top">
                <div>
                  <div class="order-id">Pedido #{oid}</div>
                  <div class="order-time">Actualizado {updated}</div>
                </div>
                <div class="badges">
                  <span class="pill {status_class(status)}">{status_safe}</span>
                  <span class="pill {pay_class(pay_status)}">{pay_safe}</span>
                </div>
              </div>

              <div class="order-main">
                <section class="customer">
                  <div class="avatar">{client[:1].upper() if client else "P"}</div>
                  <div>
                    <div class="eyebrow">CLIENTE</div>
                    <strong>{client}</strong>
                    <div class="muted">{delivery_badge} · {hora}</div>
                  </div>
                </section>

                <section class="pricebox">
                  <div class="eyebrow">TOTAL</div>
                  <div class="price">{total_safe}</div>
                </section>
              </div>

              <div class="detail-grid">
                <div class="detail">
                  <span>🍽️</span>
                  <div><small>Pedido</small><b>{pedido_safe}</b></div>
                </div>
                <div class="detail">
                  <span>📍</span>
                  <div><small>Entrega</small><b>{entrega_safe}</b></div>
                </div>
                <div class="detail">
                  <span>{payment_icon}</span>
                  <div><small>Método de pago</small><b>{metodo}</b></div>
                </div>
                <div class="detail">
                  <span>🧾</span>
                  <div><small>Referencia</small><b>#{oid}</b></div>
                </div>
              </div>

              <div class="card-actions">
                {receipt}
                <form method="post" action="/admin/order/{oid}?key={html.escape(ADMIN_KEY)}">
                  <label>Estado del pedido</label>
                  <div class="control">
                    <select name="status">{opts}</select>
                    <button class="btn primary">Actualizar</button>
                  </div>
                </form>

                <form method="post" action="/admin/order/{oid}/payment?key={html.escape(ADMIN_KEY)}">
                  <label>Estado del pago</label>
                  <div class="control">
                    <select name="payment_status">{popts}</select>
                    <button class="btn dark">Guardar pago</button>
                  </div>
                </form>
              </div>
            </article>
            '''
        )

    cards_html=''.join(cards) if cards else '''
      <div class="empty">
        <div class="empty-icon">🧾</div>
        <h3>No se encontraron pedidos</h3>
        <p>Prueba otro término de búsqueda o crea un pedido desde la demo.</p>
      </div>
    '''

    page=f'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#075e54">
<title>Panel · Punto Verde Express</title>
<style>
:root{{
  --green:#075e54;--green2:#0d7b65;--accent:#16a36f;--bg:#f3f7f5;--paper:#fff;
  --ink:#18342b;--muted:#74867f;--line:#dce8e1;--orange:#f59e0b;--red:#dc4c4c;
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--ink)}}
a{{color:inherit}}
.topbar{{
  position:sticky;top:0;z-index:20;background:linear-gradient(135deg,#064e45,#08745f);color:white;
  box-shadow:0 8px 24px rgba(18,70,55,.16)
}}
.topinner{{max-width:1180px;margin:auto;padding:14px 20px;display:flex;align-items:center;gap:12px}}
.brandmark{{width:42px;height:42px;background:#fff;border-radius:13px;display:grid;place-items:center;font-size:23px;box-shadow:0 4px 14px rgba(0,0,0,.13)}}
.brandtext{{flex:1;min-width:0}}
.brandtext b{{display:block;font-size:16px}}
.brandtext span{{font-size:11px;opacity:.82}}
.top-actions{{display:flex;gap:8px}}
.top-actions a{{text-decoration:none;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.1);padding:9px 11px;border-radius:11px;font-size:12px;font-weight:800}}
.wrap{{max-width:1180px;margin:auto;padding:22px 20px 40px}}
.hero{{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:16px}}
.hero h1{{margin:0;font-size:26px;letter-spacing:-.5px}}
.hero p{{margin:6px 0 0;color:var(--muted);font-size:13px}}
.live{{display:flex;align-items:center;gap:7px;background:#e6f8ee;color:#11714f;border:1px solid #ccebdc;padding:8px 11px;border-radius:999px;font-size:12px;font-weight:800;white-space:nowrap}}
.live::before{{content:"";width:8px;height:8px;border-radius:50%;background:#1ab77b;box-shadow:0 0 0 4px rgba(26,183,123,.12)}}
.stats{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:14px}}
.stat{{background:#fff;border:1px solid #e4ece8;border-radius:17px;padding:15px;box-shadow:0 5px 18px rgba(17,69,52,.05)}}
.stat .icon{{font-size:18px;margin-bottom:10px}}
.stat b{{display:block;font-size:25px;line-height:1;color:var(--green);letter-spacing:-.4px}}
.stat span{{display:block;margin-top:6px;color:var(--muted);font-size:11px;font-weight:700}}
.tools{{background:#fff;border:1px solid #e4ece8;border-radius:17px;padding:11px;margin-bottom:16px;display:flex;gap:10px;box-shadow:0 5px 18px rgba(17,69,52,.04)}}
.search{{display:flex;gap:8px;flex:1}}
.search input{{flex:1;border:1px solid #d7e4dd;border-radius:11px;padding:11px 12px;outline:none;font-size:13px}}
.search input:focus{{border-color:#7ac5aa;box-shadow:0 0 0 3px rgba(22,163,111,.08)}}
.btn{{border:0;border-radius:10px;padding:10px 13px;font-weight:800;cursor:pointer}}
.btn.primary{{background:#13a16d;color:#fff}}
.btn.dark{{background:#075e54;color:#fff}}
.order-card{{background:#fff;border:1px solid #e2ece6;border-radius:20px;padding:17px;margin:14px 0;box-shadow:0 8px 28px rgba(21,68,53,.06);position:relative;overflow:hidden}}
.order-card.new::before{{content:"NUEVO";position:absolute;right:-34px;top:17px;transform:rotate(42deg);background:#f59e0b;color:#fff;padding:5px 38px;font-size:9px;font-weight:900;letter-spacing:.7px}}
.order-top{{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;padding-bottom:13px;border-bottom:1px solid #edf2ef}}
.order-id{{font-weight:900;font-size:17px;color:#0a604f}}
.order-time{{font-size:10px;color:var(--muted);margin-top:4px}}
.badges{{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;padding-right:3px}}
.pill{{font-size:10px;font-weight:900;padding:6px 9px;border-radius:999px}}
.st-new{{background:#fff3dd;color:#9a5c00}} .st-ok{{background:#e9f8ef;color:#0f774d}}
.st-prep{{background:#eaf1ff;color:#355dad}} .st-ready{{background:#f1ebff;color:#6546aa}}
.st-route{{background:#e8f7ff;color:#16749e}} .st-done{{background:#e8f7ec;color:#24733b}}
.st-cancel{{background:#ffeded;color:#a93a3a}}
.pay-wait{{background:#fff5df;color:#966300}} .pay-ok{{background:#e7f7ed;color:#18764b}}
.pay-bad{{background:#ffeded;color:#a83a3a}} .pay-cash{{background:#f0f1f4;color:#4f5964}}
.order-main{{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:15px 0}}
.customer{{display:flex;align-items:center;gap:11px;min-width:0}}
.avatar{{width:43px;height:43px;border-radius:13px;background:linear-gradient(135deg,#0f8b6d,#18b67e);color:#fff;display:grid;place-items:center;font-size:18px;font-weight:900;box-shadow:0 6px 14px rgba(15,139,109,.17)}}
.eyebrow{{font-size:9px;font-weight:900;color:#8a9a94;letter-spacing:.8px;margin-bottom:3px}}
.customer strong{{font-size:14px}}
.muted{{color:var(--muted);font-size:11px;margin-top:3px}}
.pricebox{{background:#f0faf5;border:1px solid #d9eee3;border-radius:14px;padding:10px 13px;text-align:right;min-width:102px}}
.price{{font-size:18px;font-weight:900;color:#0c755a}}
.detail-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}}
.detail{{border:1px solid #e7efeb;background:#fafcfb;border-radius:13px;padding:11px;display:flex;gap:9px;min-width:0}}
.detail>span{{font-size:18px;line-height:1}}
.detail small{{display:block;color:#80908a;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px}}
.detail b{{display:block;font-size:11px;line-height:1.35;word-break:break-word}}
.card-actions{{margin-top:14px;padding-top:13px;border-top:1px solid #edf2ef;display:grid;grid-template-columns:auto 1fr 1fr;gap:10px;align-items:end}}
.card-actions form label{{display:block;font-size:9px;color:#788a83;font-weight:900;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}}
.control{{display:flex;gap:7px}}
.control select{{flex:1;min-width:0;border:1px solid #d6e3dc;border-radius:10px;padding:10px;background:#fff;font-size:11px;color:#26453a}}
.receipt{{align-self:end;text-decoration:none;background:#f4f6f5;border:1px solid #dbe6e0;color:#365d50;padding:10px 12px;border-radius:10px;font-size:11px;font-weight:900;text-align:center}}
.empty{{background:#fff;border:1px dashed #cfded6;border-radius:20px;padding:42px;text-align:center;color:#6f827a}}
.empty-icon{{font-size:34px}}
.empty h3{{margin:9px 0 4px;color:#315247}}
.empty p{{margin:0;font-size:12px}}
@media(max-width:900px){{
  .stats{{grid-template-columns:repeat(2,1fr)}} .detail-grid{{grid-template-columns:repeat(2,1fr)}}
  .card-actions{{grid-template-columns:1fr}} .receipt{{width:100%}}
}}
@media(max-width:620px){{
  .topinner{{padding:12px}} .wrap{{padding:15px 10px 30px}} .hero{{align-items:flex-start;flex-direction:column}}
  .stats{{grid-template-columns:repeat(2,1fr);gap:8px}} .stat{{padding:13px}}
  .detail-grid{{grid-template-columns:1fr 1fr}} .order-top{{flex-direction:column}}
  .badges{{justify-content:flex-start}} .order-main{{align-items:flex-start}}
  .control{{flex-direction:column}} .top-actions a:first-child{{display:none}}
  .tools,.search{{flex-direction:column}}
}}
</style>
</head>
<body>
<header class="topbar">
  <div class="topinner">
    <div class="brandmark">🌿</div>
    <div class="brandtext">
      <b>Punto Verde Express</b>
      <span>Panel de pedidos · Menús & Parrillas</span>
    </div>
    <div class="top-actions">
      <a href="/demo" target="_blank">👁️ Ver demo</a>
      <a href="/admin?key={html.escape(ADMIN_KEY)}">↻ Actualizar</a>
    </div>
  </div>
</header>

<main class="wrap">
  <section class="hero">
    <div>
      <h1>Gestión de pedidos</h1>
      <p>Controla pedidos, pagos y entregas desde un solo lugar.</p>
    </div>
    <div class="live">Sistema operativo</div>
  </section>

  <section class="stats">
    <div class="stat"><div class="icon">🧾</div><b>{total}</b><span>Pedidos registrados</span></div>
    <div class="stat"><div class="icon">🆕</div><b>{nuevos}</b><span>Pedidos nuevos</span></div>
    <div class="stat"><div class="icon">📱</div><b>{yapes}</b><span>Yapes por verificar</span></div>
    <div class="stat"><div class="icon">🛵</div><b>{en_ruta}</b><span>En camino</span></div>
    <div class="stat"><div class="icon">✅</div><b>{entregados}</b><span>Entregados</span></div>
  </section>

  <section class="tools">
    <form class="search" method="get">
      <input type="hidden" name="key" value="{html.escape(ADMIN_KEY)}">
      <input name="q" value="{html.escape(q)}" placeholder="🔎 Buscar por pedido, cliente, plato o dirección">
      <button class="btn primary">Buscar</button>
    </form>
  </section>

  {cards_html}
</main>
</body>
</html>'''
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
