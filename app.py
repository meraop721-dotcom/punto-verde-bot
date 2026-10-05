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
<meta name="theme-color" content="#0b6b56">
<title>Punto Verde Express · Demo</title>
<style>
:root{
  --green:#0b6b56;--green2:#0e8a6d;--accent:#f59e0b;--ink:#17362d;--muted:#70837b;
  --bg:#edf4f0;--paper:#fff;--line:#dce9e2;--soft:#eef9f4;--dark:#0d4135;
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:var(--ink);
  background:
    radial-gradient(circle at 8% 10%,rgba(11,107,86,.12),transparent 24%),
    radial-gradient(circle at 92% 88%,rgba(245,158,11,.10),transparent 20%),
    linear-gradient(180deg,#f9fbfa,#edf4f0);
}
button,input{font:inherit}
button{cursor:pointer}
.page{min-height:100vh;padding:0;display:block}
.layout{width:100%;min-height:100vh;display:block}
.showcase{display:none}
.showcase{
  min-height:770px;border-radius:30px;padding:32px;overflow:hidden;position:relative;
  background:linear-gradient(145deg,#073f35 0%,#0b6b56 58%,#139574 100%);
  color:#fff;box-shadow:0 26px 70px rgba(10,78,61,.19);
}
.showcase:before,.showcase:after{content:"";position:absolute;border-radius:50%;pointer-events:none}
.showcase:before{width:340px;height:340px;right:-145px;top:-135px;background:rgba(255,255,255,.08)}
.showcase:after{width:260px;height:260px;left:-150px;bottom:-120px;background:rgba(245,158,11,.09)}
.brandline{display:flex;align-items:center;gap:12px;position:relative;z-index:1}
.brandmark{width:52px;height:52px;border-radius:17px;background:#fff;display:grid;place-items:center;font-size:27px;box-shadow:0 10px 22px rgba(0,0,0,.14)}
.brandname{font-size:18px;font-weight:900}.brandmeta{font-size:11px;color:rgba(255,255,255,.68);margin-top:3px}
.hero{position:relative;z-index:1;margin-top:44px;max-width:620px}
.eyebrow{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border-radius:999px;background:rgba(255,255,255,.11);border:1px solid rgba(255,255,255,.16);font-size:10px;font-weight:900;letter-spacing:.55px}
.dot{width:7px;height:7px;border-radius:50%;background:#9ff2c5;box-shadow:0 0 0 4px rgba(159,242,197,.13)}
.hero h2{font-size:47px;line-height:1.01;letter-spacing:-1.7px;margin:17px 0 13px}
.hero p{font-size:14.5px;line-height:1.55;color:rgba(255,255,255,.82);max-width:570px;margin:0}
.cta-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:20px}
.cta{border:0;border-radius:13px;padding:12px 15px;font-size:12px;font-weight:900;background:#fff;color:var(--green);box-shadow:0 8px 22px rgba(0,0,0,.13)}
.cta.alt{background:rgba(255,255,255,.10);color:#fff;border:1px solid rgba(255,255,255,.18);box-shadow:none}
.show-card{position:relative;z-index:1;margin-top:34px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.15);border-radius:23px;padding:17px}
.show-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:13px}
.show-head strong{font-size:12px;letter-spacing:.5px;text-transform:uppercase}
.show-head span{font-size:9.5px;color:rgba(255,255,255,.62)}
.week{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}
.day{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.11);border-radius:14px;padding:11px;min-height:102px}
.day b{font-size:10px;display:block;color:#baf4d7}.day strong{display:block;margin-top:8px;font-size:11px;line-height:1.25}.day small{display:block;color:rgba(255,255,255,.60);font-size:9px;margin-top:5px;line-height:1.25}
.sat{
  margin-top:10px;padding:13px 14px;border-radius:15px;background:linear-gradient(90deg,rgba(245,158,11,.20),rgba(255,255,255,.08));
  border:1px solid rgba(245,190,85,.24);display:flex;justify-content:space-between;align-items:center;gap:12px
}
.sat b{display:block;font-size:11px}.sat span{display:block;margin-top:3px;font-size:9.5px;color:rgba(255,255,255,.67)}
.sat strong{font-size:11px;white-space:nowrap;color:#ffe4a5}
.benefits{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:13px}
.benefit{border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.07);border-radius:14px;padding:11px}
.benefit b{display:block;font-size:10.5px}.benefit span{display:block;margin-top:4px;font-size:9px;line-height:1.35;color:rgba(255,255,255,.62)}
.show-footer{position:absolute;left:32px;right:32px;bottom:25px;display:flex;justify-content:space-between;gap:10px;color:rgba(255,255,255,.58);font-size:9px}
.phone{
  width:100%;max-width:none;height:100vh;min-height:0;
  background:#fff;border:0;border-radius:0;overflow:hidden;
  box-shadow:none;display:flex;flex-direction:column;
}
.top{background:linear-gradient(135deg,#064f43,#0b765f);color:#fff;padding:15px 16px 13px}
.brandrow{display:flex;align-items:center;gap:10px}
.logo{width:43px;height:43px;border-radius:14px;background:#fff;display:grid;place-items:center;font-size:22px;flex:0 0 auto}
.brand{min-width:0;flex:1}.brand h1{margin:0;font-size:16px;font-weight:900}.sub{font-size:10px;opacity:.80;margin-top:3px}
.status{width:6px;height:6px;display:inline-block;border-radius:50%;background:#9ff2c5;margin-right:4px}
.reset{border:1px solid rgba(255,255,255,.19);background:rgba(255,255,255,.10);color:#fff;border-radius:10px;padding:8px 10px;font-size:10px;font-weight:800}
.info{display:flex;gap:6px;overflow:auto;padding:9px 10px;border-bottom:1px solid var(--line);scrollbar-width:none;background:#fff}
.info::-webkit-scrollbar{display:none}
.tag{white-space:nowrap;border:1px solid #dbe9e2;background:#f8fbfa;color:#315b4e;border-radius:999px;padding:7px 9px;font-size:10px;font-weight:900}
.chat{flex:1;min-height:0;overflow:auto;padding:14px 11px;background:#edf3ef;background-image:radial-gradient(#d6e4dc 1px,transparent 1px);background-size:18px 18px}
.msgrow{display:flex;align-items:flex-end;gap:6px;margin:8px 0}.msgrow.me{justify-content:flex-end}
.botavatar{width:26px;height:26px;border-radius:50%;background:#fff;border:1px solid #d9e5df;display:grid;place-items:center;font-size:13px;box-shadow:0 2px 7px rgba(0,0,0,.07);flex:0 0 auto}
.bubble{max-width:84%;background:#fff;border-radius:15px 15px 15px 5px;padding:9px 11px 7px;box-shadow:0 1px 2px rgba(0,0,0,.08);font-size:13px;line-height:1.43;word-break:break-word}
.me .bubble{background:#d9fdd3;border-radius:15px 15px 5px 15px}
.meta{margin-top:4px;color:#82928b;font-size:8.5px;text-align:right}
.typing{display:none;align-items:center;gap:4px;background:#fff;border-radius:13px 13px 13px 5px;padding:10px 12px;width:max-content;box-shadow:0 1px 2px rgba(0,0,0,.08);margin:6px 0 7px 32px}
.typing span{width:6px;height:6px;border-radius:50%;background:#899a92;animation:b 1.1s infinite}.typing span:nth-child(2){animation-delay:.15s}.typing span:nth-child(3){animation-delay:.3s}
@keyframes b{0%,70%,100%{transform:translateY(0);opacity:.4}35%{transform:translateY(-4px);opacity:1}}
.quick{display:flex;gap:6px;overflow:auto;padding:9px 9px;background:#fafcfb;border-top:1px solid var(--line);scrollbar-width:none}
.quick::-webkit-scrollbar{display:none}
.quick button{white-space:nowrap;border:1px solid #cfe3d9;background:#fff;color:#16634f;border-radius:999px;padding:8px 10px;font-size:10px;font-weight:900}
.composer{display:flex;align-items:center;gap:7px;padding:9px 9px;background:#fff;border-top:1px solid var(--line);padding-bottom:max(9px,env(safe-area-inset-bottom))}
.textwrap{flex:1;display:flex;align-items:center;background:#f3f6f5;border:1px solid #e0e9e5;border-radius:21px;padding:0 4px 0 9px}
.textwrap input[type=text]{flex:1;border:0;outline:0;background:transparent;padding:11px 5px;font-size:15px;min-width:0;color:#1e352d;display:block;-webkit-user-select:text;user-select:text;touch-action:manipulation}
.camera{width:33px;height:33px;display:grid;place-items:center;color:#49665c;font-size:16px;cursor:pointer}
#f{display:none}
.send{width:40px;height:40px;border-radius:50%;border:0;background:linear-gradient(135deg,#15a06c,#08745f);color:#fff;display:grid;place-items:center;font-size:16px;box-shadow:0 5px 13px rgba(8,116,95,.24)}
.phone-footer{text-align:center;padding:6px 9px;color:#91a099;background:#fff;border-top:1px solid #eef2ef;font-size:8.5px}
@media(max-width:520px){
  .phone{height:100dvh}
}
</style>
</head>
<body>
<div class="page">
  <div class="layout">
    <main class="phone">
      <header class="top">
        <div class="brandrow">
          <div class="logo">🌿</div>
          <div class="brand">
            <h1>Punto Verde Express</h1>
            <div class="sub"><span class="status"></span>En línea · respuesta automática</div>
          </div>
          <button class="reset" onclick="resetChat()">↻ Reiniciar</button>
        </div>
      </header>

      <section class="info">
        <span class="tag">🍛 Menús L–V</span>
        <span class="tag">🔥 Parrillas sábado</span>
        <span class="tag">🛵 Delivery</span>
        <span class="tag">💳 Yape / efectivo</span>
      </section>

      <section id="c" class="chat" aria-live="polite"></section>
      <div id="typing" class="typing"><span></span><span></span><span></span></div>

      <section class="quick">
        <button onclick="quick('1')">🍽️ Menú</button>
        <button onclick="quick('2')">🛒 Pedir</button>
        <button onclick="quick('3')">🔥 Parrillas</button>
        <button onclick="quick('4')">📦 Seguimiento</button>
        <button onclick="quick('5')">👤 Ayuda</button>
      </section>

      <footer class="composer">
        <div class="textwrap">
          <label class="camera" for="f" title="Enviar comprobante">📷</label>
          <input id="f" type="file" accept="image/*" onchange="img()">
          <input id="i" type="text" autocomplete="off" placeholder="Escribe un mensaje...">
        </div>
        <button class="send" onclick="s()" title="Enviar">➤</button>
      </footer>
      <div class="phone-footer">Punto Verde Express · Demo funcional para presentación</div>
    </main>
  </div>
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
    add(j.reply,'bot');
  }catch(e){
    showTyping(false);
    add('No pude cargar la imagen. Intenta otra vez.','bot');
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
  setTimeout(()=>{showTyping(false);add(j.reply,'bot',j.images||[])},300)
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


WEBPAGE="""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0a6b56">
<title>Punto Verde Express · Menús & Parrillas</title>
<style>
:root{--g:#0a6b56;--g2:#0f8d70;--deep:#063e34;--mint:#e9f7f0;--orange:#f59e0b;--ink:#17372e;--muted:#6f8179;--bg:#f5f8f6;--line:#dfeae5;--white:#fff}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;color:var(--ink);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:linear-gradient(180deg,#fbfdfc 0%,var(--bg) 100%)}
a{text-decoration:none;color:inherit}button{font:inherit;cursor:pointer}
.wrap{width:min(1120px,calc(100% - 28px));margin:auto}
.nav{position:sticky;top:0;z-index:20;background:rgba(251,253,252,.93);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.navin{height:64px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.logo{display:flex;align-items:center;gap:9px}.logoMark{width:40px;height:40px;border-radius:13px;background:linear-gradient(145deg,var(--g),var(--g2));color:#fff;display:grid;place-items:center;font-size:21px;box-shadow:0 8px 18px rgba(10,107,86,.18)}.logo strong{display:block;font-size:14px}.logo small{display:block;margin-top:2px;font-size:9px;color:var(--muted)}
.navlinks{display:none;gap:19px;font-size:11px;font-weight:900;color:#42655a}.navlinks a:hover{color:var(--g)}
.navcta{background:var(--g);color:#fff;padding:10px 12px;border-radius:11px;font-size:10.5px;font-weight:900}
.hero{padding:26px 0 20px}.heroCard{position:relative;overflow:hidden;border-radius:27px;padding:29px 23px;color:#fff;background:linear-gradient(145deg,#063e34 0%,#0a6b56 58%,#139271 100%);box-shadow:0 20px 45px rgba(8,75,59,.15)}
.heroCard:before,.heroCard:after{content:"";position:absolute;border-radius:50%;pointer-events:none}.heroCard:before{width:270px;height:270px;right:-120px;top:-120px;background:rgba(255,255,255,.08)}.heroCard:after{width:190px;height:190px;left:-120px;bottom:-110px;background:rgba(245,158,11,.1)}
.badge{position:relative;z-index:1;display:inline-flex;align-items:center;gap:7px;padding:8px 10px;border-radius:99px;background:rgba(255,255,255,.11);border:1px solid rgba(255,255,255,.16);font-size:9px;font-weight:900;letter-spacing:.45px}.dot{width:7px;height:7px;border-radius:50%;background:#a4f1c5;box-shadow:0 0 0 4px rgba(164,241,197,.12)}
.hero h1{position:relative;z-index:1;margin:17px 0 11px;max-width:700px;font-size:clamp(34px,9vw,60px);line-height:.98;letter-spacing:-1.8px}.hero p{position:relative;z-index:1;max-width:650px;margin:0;color:rgba(255,255,255,.78);font-size:13.5px;line-height:1.55}
.actions{position:relative;z-index:1;display:flex;gap:8px;flex-wrap:wrap;margin-top:19px}.btn{display:inline-flex;align-items:center;justify-content:center;border:0;border-radius:13px;padding:12px 15px;font-size:11px;font-weight:900}.btn.main{background:#fff;color:var(--g);box-shadow:0 8px 18px rgba(0,0,0,.12)}.btn.alt{color:#fff;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.17)}
.heroStats{position:relative;z-index:1;display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:22px}.stat{padding:11px;border-radius:14px;border:1px solid rgba(255,255,255,.11);background:rgba(255,255,255,.07)}.stat b{display:block;font-size:10.5px}.stat span{display:block;margin-top:4px;font-size:8.8px;color:rgba(255,255,255,.63);line-height:1.35}
.section{padding:24px 0}.head{display:flex;align-items:end;justify-content:space-between;gap:14px;margin-bottom:12px}.head h2{margin:0;font-size:22px;letter-spacing:-.5px}.head p{margin:0;color:var(--muted);font-size:9.5px;line-height:1.4;text-align:right}
.today{border:1px solid #d8e7df;background:linear-gradient(135deg,#fff,#f4fbf7);border-radius:20px;padding:16px;box-shadow:0 10px 30px rgba(18,80,61,.06)}.todayTop{display:flex;align-items:center;justify-content:space-between;gap:10px}.pill{display:inline-block;padding:7px 9px;border-radius:99px;background:#e6f5ed;color:#216d56;font-size:9px;font-weight:900}.price{font-size:18px;color:var(--g);font-weight:1000}
.grid{display:grid;grid-template-columns:1fr;gap:12px;margin-top:13px}.card{background:#fff;border:1px solid var(--line);border-radius:17px;padding:14px}.card h3{margin:0;font-size:12.5px}.card small{color:var(--muted);font-size:8.8px}.items{display:grid;gap:6px;margin-top:9px}.item{padding:8px 9px;border-radius:10px;background:#f5f9f7;font-size:10px;font-weight:800}.buy{width:100%;margin-top:11px;padding:10px;border:1px solid #cfe1d8;border-radius:11px;background:#fff;color:var(--g);font-size:10px;font-weight:900}
.week{display:grid;grid-template-columns:1fr;gap:9px}.day{padding:14px;background:#fff;border:1px solid var(--line);border-radius:16px}.dayTop{display:flex;justify-content:space-between;align-items:center}.dayTop b{font-size:10px;color:var(--g);letter-spacing:.35px}.dayTop span{font-size:8.5px;color:var(--muted)}.day strong{display:block;margin-top:8px;font-size:11.5px}.day small{display:block;margin-top:4px;font-size:9px;color:var(--muted);line-height:1.4}
.sat{border-radius:19px;padding:16px;color:#fff;background:linear-gradient(135deg,#51330d,#9a6011 72%,#c47d16);box-shadow:0 12px 28px rgba(118,73,9,.13)}.sat h3{margin:0;font-size:14px}.sat p{margin:4px 0 0;color:rgba(255,255,255,.72);font-size:9px}.satGrid{display:grid;grid-template-columns:1fr;gap:7px;margin-top:12px}.satItem{padding:10px 11px;border-radius:11px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.15);font-size:10px;font-weight:900}.sat .btn{margin-top:12px}
.how{display:grid;grid-template-columns:1fr;gap:9px}.step{padding:14px;background:#fff;border:1px solid var(--line);border-radius:16px}.num{width:28px;height:28px;border-radius:9px;background:#e7f5ee;color:var(--g);display:grid;place-items:center;font-size:10px;font-weight:1000}.step h3{margin:9px 0 4px;font-size:12px}.step p{margin:0;color:var(--muted);font-size:9px;line-height:1.45}
.ctaBox{margin-top:4px;margin-bottom:8px;border-radius:21px;padding:20px;background:linear-gradient(135deg,#073f35,#0b735d);color:#fff}.ctaBox h2{margin:0;font-size:20px}.ctaBox p{margin:6px 0 0;color:rgba(255,255,255,.72);font-size:10px;line-height:1.45}
.footer{padding:17px 0 78px;border-top:1px solid var(--line);color:var(--muted);font-size:9px}.foot{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.bottom{position:fixed;left:0;right:0;bottom:0;z-index:40;display:flex;gap:7px;padding:8px 10px calc(8px + env(safe-area-inset-bottom));background:rgba(251,253,252,.95);backdrop-filter:blur(12px);border-top:1px solid var(--line)}.bottom a{flex:1;text-align:center;padding:11px 6px;border-radius:11px;background:#fff;border:1px solid var(--line);color:var(--g);font-size:9.5px;font-weight:900}.bottom a.main{background:var(--g);border-color:var(--g);color:#fff}
@media(min-width:700px){
  .wrap{width:min(1120px,calc(100% - 40px))}.navlinks{display:flex}.navcta{display:none}.hero{padding-top:40px}.heroCard{padding:43px}.heroStats{grid-template-columns:repeat(4,1fr)}.grid{grid-template-columns:1fr 1fr}.week{grid-template-columns:repeat(5,1fr)}.satGrid{grid-template-columns:repeat(3,1fr)}.how{grid-template-columns:repeat(3,1fr)}.bottom{display:none}.footer{padding-bottom:25px}
}
</style>
</head>
<body>
<header class="nav"><div class="wrap navin">
<a class="logo" href="#inicio"><div class="logoMark">🌿</div><div><strong>Punto Verde Express</strong><small>Menús & Parrillas · Guadalupe y Chepén</small></div></a>
<nav class="navlinks"><a href="#menu">Menú</a><a href="#semana">Semana</a><a href="#parrillas">Sábado</a><a href="#como">Cómo funciona</a></nav>
<a class="navcta" href="/demo">Pedir ahora</a>
</div></header>

<main id="inicio">
<section class="hero"><div class="wrap"><div class="heroCard">
<span class="badge"><span class="dot"></span> PEDIDOS RÁPIDOS DESDE EL CELULAR</span>
<h1>Comida casera, fácil de pedir.</h1>
<p>Conoce el menú, revisa las opciones del día y pasa al bot para confirmar tu pedido, elegir recojo o delivery y consultar el estado.</p>
<div class="actions"><a class="btn main" href="/demo">🛒 Pedir ahora</a><a class="btn alt" href="#menu">🍛 Ver menú</a></div>
<div class="heroStats">
<div class="stat"><b>🍛 Menús L–V</b><span>Opciones caseras y criollas.</span></div><div class="stat"><b>🔥 Parrillas sábado</b><span>Especial para compartir.</span></div><div class="stat"><b>🛵 Delivery</b><span>Guadalupe y Chepén.</span></div><div class="stat"><b>📦 Seguimiento</b><span>Consulta tu pedido.</span></div>
</div>
</div></div></section>

<section id="menu" class="section"><div class="wrap"><div class="head"><div><h2>Menú de hoy</h2><p style="text-align:left">Actualizado automáticamente por día.</p></div><span class="pill">Precio referencial</span></div><div class="today">__TODAY__</div></div></section>

<section id="semana" class="section"><div class="wrap"><div class="head"><div><h2>Menú semanal</h2></div><p>Lunes a viernes<br>Entradas + segundos</p></div><div class="week">__WEEK__</div></div></section>

<section id="parrillas" class="section"><div class="wrap"><div class="sat"><h3>🔥 Sábado de parrillas</h3><p>Una opción especial para compartir.</p><div class="satGrid"><div class="satItem">🍗 Pollo a la parrilla</div><div class="satItem">🥩 Parrilla familiar</div><div class="satItem">🔥 Chorizo + pollo + carne</div></div><a class="btn main" href="/demo">Reservar / pedir</a></div></div></section>

<section id="como" class="section"><div class="wrap"><div class="head"><div><h2>Así funciona</h2></div><p>En pocos pasos.</p></div><div class="how"><div class="step"><div class="num">01</div><h3>Consulta</h3><p>Revisa el menú y conoce las opciones disponibles.</p></div><div class="step"><div class="num">02</div><h3>Elige</h3><p>Selecciona tu comida, modalidad, hora y pago.</p></div><div class="step"><div class="num">03</div><h3>Confirma</h3><p>Obtén tu número de pedido y haz seguimiento.</p></div></div></div></section>

<section class="section"><div class="wrap"><div class="ctaBox"><h2>¿Listo para pedir?</h2><p>Entra al bot de Punto Verde Express y completa tu pedido desde el celular.</p><div class="actions"><a class="btn main" href="/demo">🛒 Ir al bot</a></div></div></div></section>
</main>

<footer class="footer"><div class="wrap foot"><span>🌿 Punto Verde Express</span><span>Guadalupe y Chepén · Prototipo funcional</span></div></footer>
<div class="bottom"><a href="#menu">🍛 Menú</a><a class="main" href="/demo">🛒 Pedir</a><a href="#parrillas">🔥 Sábado</a></div>
</body>
</html>"""

def web_today_html(day):
    if day in MENUS:
        m=MENUS[day]
        entries=''.join('<div class="item">'+html.escape(x)+'</div>' for x in m['entradas'])
        mains=''.join('<div class="item">'+html.escape(x)+'</div>' for x in m['segundos'])
        price=money(MENU_PRICE)
        return '<div class="todayTop"><div><span class="pill">'+html.escape(m['dia'].upper())+'</span><div style="font-size:17px;font-weight:900;margin-top:9px">Opciones disponibles</div></div><div class="price">'+html.escape(price)+'</div></div><div class="grid"><div class="card"><h3>🥣 Entradas</h3><small>Elige 1</small><div class="items">'+entries+'</div></div><div class="card"><h3>🍛 Segundos</h3><small>Elige 1</small><div class="items">'+mains+'</div></div></div><a class="buy" href="/demo">🛒 Pedir este menú</a>'
    if day==5:
        grill_price=money(SATURDAY_GRILL_PRICE) if SATURDAY_GRILL_PRICE else 'Por confirmar'
        return '<div class="todayTop"><div><span class="pill">SÁBADO</span><div style="font-size:17px;font-weight:900;margin-top:9px">Especial de parrillas 🔥</div></div><div class="price" style="font-size:14px">'+html.escape(grill_price)+'</div></div><div class="grid"><div class="card"><h3>🍗 Pollo a la parrilla</h3><small>Especial del sábado</small></div><div class="card"><h3>🥩 Parrilla familiar</h3><small>Para compartir</small></div></div><a class="buy" href="/demo">🔥 Reservar / pedir</a>'
    return '<div class="todayTop"><div><span class="pill">DOMINGO</span><div style="font-size:17px;font-weight:900;margin-top:9px">Hoy no hay atención programada</div></div></div><p style="margin:10px 0 0;color:var(--muted);font-size:10px">Vuelve el lunes para consultar el nuevo menú.</p>'

def web_week_html():
    cards=[]
    for _,m in MENUS.items():
        cards.append('<article class="day"><div class="dayTop"><b>'+html.escape(m['dia'].upper())+'</b><span>Menú</span></div><strong>'+html.escape(m['segundos'][0])+'</strong><small>'+html.escape(m['segundos'][1])+' · '+html.escape(m['segundos'][2])+'</small></article>')
    return ''.join(cards)

@app.get('/')
def home():
    day=datetime.now(TZ).weekday()
    page=WEBPAGE.replace('__TODAY__',web_today_html(day)).replace('__WEEK__',web_week_html())
    return page

@app.get('/pagina')
def pagina():
    day=datetime.now(TZ).weekday()
    page=WEBPAGE.replace('__TODAY__',web_today_html(day)).replace('__WEEK__',web_week_html())
    return page

@app.get('/api/status')
def api_status():
    return jsonify({'name':'Punto Verde Express Bot','status':'ok','page':'/','demo':'/demo','meta_webhook':'/webhook','waia_webhook':'/waia-webhook'})
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
    status_filter=(request.args.get('status') or '').strip()
    payment_filter=(request.args.get('pay') or '').strip()

    allowed=['Pedido recibido','Confirmado','En preparación','Listo para recojo','En camino','Entregado','Cancelado']
    pay_allowed=['Pendiente de verificación','Pago verificado','Pago rechazado','Pago al entregar','Pagado']

    with db() as c:
        rows=c.execute(
            'SELECT id,phone,details,status,created_at,updated_at FROM orders ORDER BY id DESC LIMIT 150'
        ).fetchall()

    total=len(rows)
    nuevos=sum(1 for r in rows if r[3]=='Pedido recibido')
    en_ruta=sum(1 for r in rows if r[3]=='En camino')
    entregados=sum(1 for r in rows if r[3]=='Entregado')
    yapes=0
    hoy=0

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

    def iso_date(value):
        try:
            return datetime.fromisoformat(value).astimezone(TZ).date()
        except Exception:
            return None

    def order_total(details):
        if details.get('entrada'):
            return total_numeric(details.get('modo'),details.get('zona')) or 0.0
        try:
            return float(str(SATURDAY_GRILL_PRICE).replace('S/','').strip())
        except Exception:
            return 0.0

    today=datetime.now(TZ).date()
    for oid,phone,details_json,status,created_at,updated_at in rows:
        try:
            d=json.loads(details_json or '{}')
        except Exception:
            d={}
        if d.get('pago')=='Yape' and order_payment_status(d)=='Pendiente de verificación':
            yapes+=1
        if iso_date(created_at)==today and status!='Cancelado':
            hoy+=order_total(d)

    cards=[]
    step_names=['Pedido recibido','Confirmado','En preparación','Listo para recojo','En camino','Entregado']

    for oid,phone,details_json,status,created_at,updated_at in rows:
        try:
            d=json.loads(details_json or '{}')
        except Exception:
            d={}

        pay_status=order_payment_status(d)

        blob=' '.join([
            str(oid),str(phone),d.get('cliente',''),d.get('entrada',''),
            d.get('segundo',''),d.get('direccion',''),status,pay_status
        ]).lower()

        if q and q not in blob:
            continue
        if status_filter and status!=status_filter:
            continue
        if payment_filter and pay_status!=payment_filter:
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
                '📸 Ver comprobante</a>'
            )

        phone_clean=''.join(ch for ch in str(phone) if ch.isdigit())
        whatsapp=''
        if phone_clean and phone_clean!='' and not str(phone).startswith('demo'):
            whatsapp=f'<a class="wa" target="_blank" href="https://wa.me/{phone_clean}">💬 WhatsApp</a>'

        client=html.escape(d.get('cliente','Sin nombre'))
        pedido_safe=html.escape(pedido)
        entrega_safe=html.escape(entrega)
        total_safe=html.escape(str(total_order))
        metodo=html.escape(d.get('pago','Sin registrar'))
        status_safe=html.escape(status)
        pay_safe=html.escape(pay_status)
        hora=html.escape(d.get('hora','Sin horario'))
        phone_safe=html.escape(str(phone))
        updated=html.escape(pretty_time(updated_at or created_at))
        is_new=' new' if status=='Pedido recibido' else ''

        timeline=[]
        if status=='Cancelado':
            timeline=['<div class="cancel-state">❌ Este pedido fue cancelado.</div>']
        else:
            current_index=step_names.index(status) if status in step_names else 0
            for i,name in enumerate(step_names):
                cls='done' if i<current_index else ('active' if i==current_index else '')
                timeline.append(
                    f'<div class="tl-step {cls}"><span>{i+1}</span><small>{html.escape(name)}</small></div>'
                )
            timeline_html='<div class="timeline">'+''.join(timeline)+'</div>'
            timeline= [timeline_html]

        payment_alert=''
        if d.get('pago')=='Yape' and pay_status=='Pendiente de verificación':
            payment_alert='<div class="payment-alert">⚠️ <div><b>Yape pendiente de verificación</b><span>Revisa el comprobante antes de confirmar el pedido.</span></div></div>'

        cards.append(
            f'''
            <article class="order-card{is_new}">
              <div class="order-top">
                <div>
                  <div class="order-id">Pedido #{oid}</div>
                  <div class="order-time">{updated}</div>
                </div>
                <div class="badges">
                  <span class="pill {status_class(status)}">{status_safe}</span>
                  <span class="pill {pay_class(pay_status)}">{pay_safe}</span>
                </div>
              </div>

              {payment_alert}

              <div class="order-main">
                <section class="customer">
                  <div class="avatar">{client[:1].upper() if client else "P"}</div>
                  <div class="customer-info">
                    <div class="eyebrow">CLIENTE</div>
                    <strong>{client}</strong>
                    <div class="muted">{delivery_badge} · {hora}</div>
                    <div class="phone-line">📱 {phone_safe} {whatsapp}</div>
                  </div>
                </section>
                <section class="pricebox">
                  <div class="eyebrow">TOTAL</div>
                  <div class="price">{total_safe}</div>
                </section>
              </div>

              <div class="detail-grid">
                <div class="detail"><span>🍽️</span><div><small>Pedido</small><b>{pedido_safe}</b></div></div>
                <div class="detail"><span>📍</span><div><small>Entrega</small><b>{entrega_safe}</b></div></div>
                <div class="detail"><span>{'📱' if d.get('pago')=='Yape' else '💵'}</span><div><small>Pago</small><b>{metodo}</b></div></div>
                <div class="detail"><span>🧾</span><div><small>Referencia</small><b>#{oid}</b></div></div>
              </div>

              {''.join(timeline)}

              <div class="card-actions">
                <div class="link-actions">{receipt}{whatsapp}</div>
                <form method="post" action="/admin/order/{oid}?key={html.escape(ADMIN_KEY)}">
                  <label>Estado del pedido</label>
                  <div class="control"><select name="status">{opts}</select><button class="btn primary">Actualizar</button></div>
                </form>
                <form method="post" action="/admin/order/{oid}/payment?key={html.escape(ADMIN_KEY)}">
                  <label>Estado del pago</label>
                  <div class="control"><select name="payment_status">{popts}</select><button class="btn dark">Guardar pago</button></div>
                </form>
              </div>
            </article>
            '''
        )

    cards_html=''.join(cards) if cards else '''
      <div class="empty">
        <div class="empty-icon">🧾</div>
        <h3>No se encontraron pedidos</h3>
        <p>Prueba otro filtro o crea un pedido desde la demo.</p>
      </div>
    '''

    key=html.escape(ADMIN_KEY)
    status_options='<option value="">Todos los estados</option>'+''.join(
        '<option value="'+html.escape(s)+'"'+(' selected' if s==status_filter else '')+'>'+html.escape(s)+'</option>'
        for s in allowed
    )
    pay_options='<option value="">Todos los pagos</option>'+''.join(
        '<option value="'+html.escape(s)+'"'+(' selected' if s==payment_filter else '')+'>'+html.escape(s)+'</option>'
        for s in pay_allowed
    )

    page="""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#075e54">
<title>Panel · Punto Verde Express</title>
<style>
:root{
 --g:#075e54;--g2:#0d7b65;--mint:#e8f7f0;--ink:#18342b;--muted:#74867f;--bg:#f2f6f4;
 --line:#dce8e1;--orange:#f59e0b;--red:#c84747;--blue:#3978c8;--purple:#7354b9;
}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--ink)}
a{text-decoration:none}.topbar{position:sticky;top:0;z-index:30;background:linear-gradient(135deg,#064e45,#08745f);color:#fff;box-shadow:0 8px 28px rgba(17,70,55,.16)}
.topinner{max-width:1220px;margin:auto;padding:13px 18px;display:flex;align-items:center;gap:11px}.brandmark{width:42px;height:42px;border-radius:13px;background:#fff;display:grid;place-items:center;font-size:22px;box-shadow:0 5px 14px rgba(0,0,0,.12)}
.brandtext{flex:1;min-width:0}.brandtext b{display:block;font-size:16px}.brandtext span{display:block;margin-top:2px;font-size:10px;opacity:.78}.top-actions{display:flex;gap:7px}.top-actions a{padding:9px 11px;border:1px solid rgba(255,255,255,.20);border-radius:10px;color:#fff;background:rgba(255,255,255,.08);font-size:10px;font-weight:900}
.shell{max-width:1220px;margin:auto;padding:20px 18px 45px}.hero{display:flex;align-items:end;justify-content:space-between;gap:15px;margin-bottom:15px}.hero h1{margin:0;font-size:27px;letter-spacing:-.6px}.hero p{margin:5px 0 0;color:var(--muted);font-size:11px}.live{padding:8px 10px;border-radius:99px;background:#e7f8ef;color:#11734f;border:1px solid #cdebdc;font-size:10px;font-weight:900;white-space:nowrap}.live:before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:#1bb77c;margin-right:5px;box-shadow:0 0 0 4px rgba(27,183,124,.12)}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:12px}.stat{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px;box-shadow:0 5px 20px rgba(18,70,55,.04)}.stat .top{display:flex;justify-content:space-between;align-items:center}.stat .icon{font-size:17px}.stat b{display:block;margin-top:8px;font-size:25px;line-height:1;color:var(--g)}.stat span{display:block;margin-top:6px;color:var(--muted);font-size:10px;font-weight:800}.sales{border-left:3px solid var(--g)}.sales b{font-size:21px}
.toolbar{background:#fff;border:1px solid var(--line);border-radius:17px;padding:11px;margin-bottom:16px;box-shadow:0 5px 20px rgba(18,70,55,.035)}
.filters{display:grid;grid-template-columns:1.6fr .9fr .9fr auto auto;gap:7px}.field{border:1px solid #d7e4dd;border-radius:10px;background:#fff;padding:10px 11px;color:#29483d;font-size:11px;outline:0;min-width:0}.field:focus{border-color:#77bea6;box-shadow:0 0 0 3px rgba(22,163,111,.08)}
.btn{border:0;border-radius:10px;padding:10px 12px;font-size:10.5px;font-weight:900}.primary{background:#12a16d;color:#fff}.neutral{background:#eef3f1;color:#2b5548;border:1px solid #d9e5df}
.toolbar-note{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:8px;color:#81918a;font-size:9px}.count{font-weight:900;color:#45665a}
.order-card{background:#fff;border:1px solid #dfe9e4;border-radius:20px;padding:16px;margin:13px 0;box-shadow:0 8px 28px rgba(18,70,55,.055);position:relative;overflow:hidden}.order-card.new{border-color:#f1d29b;box-shadow:0 9px 30px rgba(180,122,20,.09)}.order-card.new:before{content:"NUEVO";position:absolute;right:-31px;top:15px;transform:rotate(42deg);background:var(--orange);color:#fff;padding:5px 36px;font-size:8px;font-weight:1000;letter-spacing:.7px}
.order-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:12px;border-bottom:1px solid #edf2ef}.order-id{font-size:16px;font-weight:1000;color:#08624f}.order-time{margin-top:3px;color:var(--muted);font-size:9px}.badges{display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap}.pill{padding:6px 9px;border-radius:99px;font-size:8.8px;font-weight:1000}.st-new{background:#fff2db;color:#965a00}.st-ok{background:#e9f8ef;color:#11724c}.st-prep{background:#eaf0ff;color:#355fae}.st-ready{background:#f2ecff;color:#674aa7}.st-route{background:#e8f7ff;color:#176f99}.st-done{background:#e8f7ec;color:#24743e}.st-cancel{background:#ffeded;color:#a83d3d}.pay-wait{background:#fff4dc;color:#966000}.pay-ok{background:#e7f7ed;color:#18764c}.pay-bad{background:#ffeded;color:#a83a3a}.pay-cash{background:#eef0f3;color:#4c5964}
.payment-alert{display:flex;align-items:center;gap:9px;margin:12px 0 0;padding:10px 11px;border-radius:12px;background:#fff7e7;border:1px solid #f3dcae;color:#8c5d09;font-size:12px}.payment-alert b{display:block;font-size:10px}.payment-alert span{display:block;margin-top:3px;font-size:9px;color:#9b7a3b}
.order-main{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 0}.customer{display:flex;align-items:center;gap:10px;min-width:0}.avatar{width:42px;height:42px;border-radius:13px;background:linear-gradient(135deg,#0d8b6d,#18b67e);display:grid;place-items:center;color:#fff;font-size:17px;font-weight:1000;box-shadow:0 6px 15px rgba(13,139,109,.16)}.customer-info{min-width:0}.eyebrow{font-size:8px;font-weight:1000;color:#899a93;letter-spacing:.8px}.customer strong{display:block;margin-top:2px;font-size:13px}.muted{margin-top:3px;color:var(--muted);font-size:9.5px}.phone-line{margin-top:4px;color:#80908a;font-size:9px}.wa{display:inline-block;margin-left:4px;color:#168c5f;font-weight:900}
.pricebox{min-width:95px;padding:10px 12px;text-align:right;border-radius:13px;background:#effaf5;border:1px solid #d9eee3}.price{margin-top:3px;font-size:18px;font-weight:1000;color:#0b765b}
.detail-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.detail{display:flex;gap:8px;padding:10px;border:1px solid #e7efeb;background:#fafcfb;border-radius:12px;min-width:0}.detail>span{font-size:16px;line-height:1}.detail small{display:block;font-size:8px;text-transform:uppercase;letter-spacing:.45px;font-weight:900;color:#82928c}.detail b{display:block;margin-top:4px;font-size:10px;line-height:1.35;word-break:break-word}
.timeline{display:grid;grid-template-columns:repeat(6,1fr);gap:4px;margin:14px 0 3px;padding:11px 8px;background:#f8faf9;border:1px solid #edf2ef;border-radius:13px}.tl-step{position:relative;text-align:center;color:#a0aaa5}.tl-step:not(:last-child):after{content:"";position:absolute;top:9px;right:-3px;width:100%;height:2px;background:#e6ece8;z-index:0}.tl-step span{position:relative;z-index:1;width:19px;height:19px;margin:auto;display:grid;place-items:center;border-radius:50%;background:#e7ece9;color:#7c8b85;font-size:8px;font-weight:1000;border:2px solid #f8faf9}.tl-step small{display:block;margin-top:5px;font-size:7px;line-height:1.2}.tl-step.done,.tl-step.active{color:var(--g);font-weight:900}.tl-step.done span,.tl-step.active span{background:var(--g);color:#fff;border-color:var(--g)}.tl-step.done:after{background:#71c6a6}.tl-step.active small{color:var(--g)}.cancel-state{margin:12px 0 2px;padding:10px 11px;border-radius:12px;background:#fff0f0;color:#a43b3b;border:1px solid #f1cccc;font-size:10px;font-weight:900}
.card-actions{margin-top:13px;padding-top:12px;border-top:1px solid #edf2ef;display:grid;grid-template-columns:auto 1fr 1fr;gap:9px;align-items:end}.link-actions{display:flex;flex-direction:column;gap:7px}.receipt,.wa{display:block;text-align:center;padding:9px 10px;border-radius:10px;background:#f3f7f5;border:1px solid #dce7e1;font-size:9px;font-weight:1000;color:#376155}.link-actions .wa{margin-left:0}.card-actions label{display:block;margin-bottom:5px;font-size:8px;text-transform:uppercase;letter-spacing:.6px;font-weight:1000;color:#788a83}.control{display:flex;gap:6px}.control select{flex:1;min-width:0;border:1px solid #d6e3dc;border-radius:10px;padding:9px;background:#fff;font-size:10px;color:#26453a}.control .primary{white-space:nowrap}.btn.dark{background:var(--g);color:#fff}
.empty{background:#fff;border:1px dashed #cfded6;border-radius:20px;padding:44px 20px;text-align:center;color:#6f827a}.empty-icon{font-size:32px}.empty h3{margin:9px 0 4px;color:#315247}.empty p{margin:0;font-size:11px}
@media(max-width:950px){.stats{grid-template-columns:repeat(3,1fr)}.filters{grid-template-columns:1fr 1fr 1fr}.filters .search{grid-column:1/-1}.filters .btn{min-height:39px}.detail-grid{grid-template-columns:repeat(2,1fr)}.card-actions{grid-template-columns:1fr}.link-actions{display:grid;grid-template-columns:1fr 1fr}.timeline{grid-template-columns:repeat(6,1fr)}}
@media(max-width:620px){.topinner{padding:11px 12px}.top-actions a:first-child{display:none}.shell{padding:14px 10px 30px}.hero{align-items:flex-start;flex-direction:column}.hero h1{font-size:23px}.live{font-size:9px}.stats{grid-template-columns:repeat(2,1fr);gap:7px}.stat{padding:11px}.stat b{font-size:22px}.sales b{font-size:19px}.filters{grid-template-columns:1fr}.filters .search{grid-column:auto}.toolbar-note{align-items:flex-start;flex-direction:column}.order-card{padding:14px;border-radius:17px}.order-top{flex-direction:column}.badges{justify-content:flex-start}.order-main{align-items:flex-start}.pricebox{min-width:90px}.detail-grid{grid-template-columns:1fr 1fr}.timeline{gap:2px;padding:9px 4px}.tl-step small{font-size:6.5px}.card-actions{grid-template-columns:1fr}.link-actions{grid-template-columns:1fr 1fr}.control{flex-direction:column}}
</style>
</head>
<body>
<header class="topbar">
  <div class="topinner">
    <div class="brandmark">🌿</div>
    <div class="brandtext"><b>Punto Verde Express</b><span>Panel de gestión de pedidos</span></div>
    <div class="top-actions"><a href="/demo">🤖 Bot</a><a href="/">🌐 Página</a><a href="/admin?key=__KEY__">↻ Actualizar</a></div>
  </div>
</header>

<main class="shell">
  <section class="hero">
    <div><h1>Centro de pedidos</h1><p>Controla pedidos, pagos y entregas desde un solo lugar.</p></div>
    <div class="live">Panel activo</div>
  </section>

  <section class="stats">
    <div class="stat"><div class="top"><span class="icon">🧾</span></div><b>__TOTAL__</b><span>Pedidos registrados</span></div>
    <div class="stat"><div class="top"><span class="icon">🆕</span></div><b>__NUEVOS__</b><span>Pedidos nuevos</span></div>
    <div class="stat"><div class="top"><span class="icon">📱</span></div><b>__YAPES__</b><span>Yapes por verificar</span></div>
    <div class="stat"><div class="top"><span class="icon">🛵</span></div><b>__RUTA__</b><span>Pedidos en camino</span></div>
    <div class="stat sales"><div class="top"><span class="icon">💰</span></div><b>__VENTAS_HOY__</b><span>Ventas no canceladas de hoy</span></div>
  </section>

  <section class="toolbar">
    <form method="get" class="filters">
      <input type="hidden" name="key" value="__KEY__">
      <input class="field search" name="q" value="__Q__" placeholder="🔎 Buscar pedido, cliente, plato, teléfono o dirección">
      <select class="field" name="status">__STATUS_OPTIONS__</select>
      <select class="field" name="pay">__PAY_OPTIONS__</select>
      <button class="btn primary" type="submit">Filtrar</button>
      <a class="btn neutral" href="/admin?key=__KEY__">Limpiar</a>
    </form>
    <div class="toolbar-note"><span>Mostrando <b class="count">__MOSTRANDO__</b> pedidos de la lista reciente.</span><span>Actualización automática cada 45 s.</span></div>
  </section>

  __CARDS__
</main>

<script>
setInterval(function(){ if(!document.hidden){ location.reload(); } },45000);
</script>
</body>
</html>"""

    page=page.replace('__KEY__',key)
    page=page.replace('__TOTAL__',str(total))
    page=page.replace('__NUEVOS__',str(nuevos))
    page=page.replace('__YAPES__',str(yapes))
    page=page.replace('__RUTA__',str(en_ruta))
    page=page.replace('__VENTAS_HOY__',money(hoy))
    page=page.replace('__Q__',html.escape(request.args.get('q') or ''))
    page=page.replace('__STATUS_OPTIONS__',status_options)
    page=page.replace('__PAY_OPTIONS__',pay_options)
    page=page.replace('__MOSTRANDO__',str(len(cards)))
    page=page.replace('__CARDS__',cards_html)

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
