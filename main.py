<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>HackerChat</title>
<style>
  :root {
    --bg:#000; --ink:#0f0; --panel:#010; --line:#0f0;
  }
  * { box-sizing:border-box; }
  body { margin:0; font-family:monospace; background:var(--bg); color:var(--ink);}
  #header { padding:10px; border-bottom:1px solid var(--line); background:var(--panel); display:flex; justify-content:space-between; align-items:center;}
  #container { display:flex; height:calc(100vh - 40px);}
  #users { width:240px; background:var(--panel); border-right:1px solid var(--line); overflow-y:auto;}
  #chat { flex:1; display:flex; flex-direction:column; }
  #topicBar { padding:8px 10px; border-bottom:1px solid var(--line); background:#000; font-weight:bold; }
  #messages { flex:1; padding:10px; overflow-y:auto; }
  #inputForm { display:flex; gap:6px; border-top:1px solid var(--line); padding:8px; }
  #inputForm input, #inputForm button { background:#000; color:var(--ink); border:1px solid var(--line); padding:6px 8px; }
  #loginForm, #registerForm, #adminForm { padding:20px; }
  .hidden { display:none; }
  button { cursor:pointer; }
  #messages .line { margin-bottom:6px; }
  #messages .me { color:#9f9; }
  #users .item { padding:8px 10px; border-bottom:1px solid #060; cursor:pointer; }
  #users .item.active { background:#020; font-weight:bold; }
  #users .item .tag { opacity:.8; font-size:12px; }
  .toolbar { display:flex; gap:8px; }
</style>
</head>
<body>

<div id="header">
  <span id="userInfo">Not logged in</span>
  <div class="toolbar">
    <button id="loginBtn">Login</button>
    <button id="adminBtn">Admin</button>
    <button id="logoutBtn" class="hidden">Logout</button>
  </div>
</div>

<div id="container">
  <div id="users"></div>
  <div id="chat">
    <div id="topicBar">🌐 Global chat</div>
    <div id="messages"></div>
    <form id="inputForm" class="hidden">
      <input id="messageInput" type="text" placeholder="Type a message and press Enter…" autocomplete="off" />
      <button type="submit">Send</button>
    </form>
  </div>
</div>

<!-- Auth Forms -->
<div id="loginForm" class="hidden">
  <h3>Login</h3>
  <input id="loginName" placeholder="Login"><br><br>
  <input id="loginPass" type="password" placeholder="Password"><br><br>
  <button type="button" onclick="doLogin()">Login</button>
  <button type="button" onclick="showRegister()">Register</button>
</div>

<div id="registerForm" class="hidden">
  <h3>Register</h3>
  <input id="regName" placeholder="Login"><br><br>
  <input id="regPass" type="password" placeholder="Password"><br><br>
  <button type="button" onclick="doRegister()">Register</button>
  <button type="button" onclick="showLogin()">Back</button>
</div>

<div id="adminForm" class="hidden">
  <h3>Admin</h3>
  <input id="adminPwd" type="password" placeholder="Password"><br><br>
  <button type="button" onclick="adminLogin()">Enter</button>
</div>

<script>
const SERVER = window.location.origin;

let currentUser = null;     // { user_id, username }
let adminPwd = null;
let selectedScope = "global";  // "global" | "dialog"
let selectedPeer = "all";      // "all" | user_id
let pollTimer = null;

// ---------- UI helpers ----------
function showLogin(){ hideAll(); document.getElementById("loginForm").classList.remove("hidden"); }
function showRegister(){ hideAll(); document.getElementById("registerForm").classList.remove("hidden"); }
function showAdmin(){ hideAll(); document.getElementById("adminForm").classList.remove("hidden"); }
function hideAll(){ document.querySelectorAll("#loginForm,#registerForm,#adminForm").forEach(e=>e.classList.add("hidden")); }
function setTopic(text){ document.getElementById("topicBar").textContent = text; }
function setAuthUI(logged){
  document.getElementById("inputForm").classList.toggle("hidden", !logged);
  document.getElementById("logoutBtn").classList.toggle("hidden", !logged);
}

function el(tag, cls, text){
  const n = document.createElement(tag);
  if(cls) n.className = cls;
  if(text!=null) n.textContent = text;
  return n;
}

// ---------- Auth ----------
async function doLogin(){
  const login = document.getElementById("loginName").value.trim();
  const pass  = document.getElementById("loginPass").value;
  const r = await fetch(SERVER+"/login", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({login, password: pass})
  });
  const d = await r.json();
  if(d.error){ alert(d.error); return; }
  currentUser = d;
  document.getElementById("userInfo").textContent = "Logged as " + d.username;
  setAuthUI(true);
  hideAll();
  await refreshUsers();
  selectGlobal();
  startPolling();
}

async function doRegister(){
  const login = document.getElementById("regName").value.trim();
  const pass  = document.getElementById("regPass").value;
  const r = await fetch(SERVER+"/register", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({login, password: pass})
  });
  const d = await r.json();
  if(d.error){ alert(d.error); return; }
  alert("Registered. Now login.");
  showLogin();
}

async function doLogout(){
  stopPolling();
  currentUser = null;
  selectedScope = "global";
  selectedPeer = "all";
  document.getElementById("userInfo").textContent = "Not logged in";
  document.getElementById("messages").innerHTML = "";
  document.getElementById("users").innerHTML = "";
  setTopic("🌐 Global chat");
  setAuthUI(false);
  showLogin();
}

// ---------- Users ----------
async function refreshUsers(){
  if(!currentUser) return;
  const r = await fetch(SERVER + "/users?exclude_id=" + encodeURIComponent(currentUser.user_id));
  const d = await r.json();
  const box = document.getElementById("users");
  box.innerHTML = "";

  // Global chat item
  const globalItem = el("div", "item" + (selectedPeer==="all" ? " active" : ""), "🌐 Global chat");
  globalItem.onclick = selectGlobal;
  box.appendChild(globalItem);

  // Users
  d.users.forEach(u=>{
    const item = el("div", "item" + (selectedPeer===u.id ? " active" : ""), u.username);
    const tag = el("div", "tag", u.id);
    item.appendChild(tag);
    item.onclick = ()=> selectPeer(u.id, u.username);
    box.appendChild(item);
  });
}

function markActivePeer(){
  const items = document.querySelectorAll("#users .item");
  items.forEach(i => i.classList.remove("active"));
  if(selectedPeer==="all"){
    items[0]?.classList.add("active");
  } else {
    // match by tag text (id)
    items.forEach(i=>{
      const idDiv = i.querySelector(".tag");
      if(idDiv && idDiv.textContent === selectedPeer) i.classList.add("active");
    });
  }
}

function selectGlobal(){
  selectedScope = "global";
  selectedPeer  = "all";
  setTopic("🌐 Global chat");
  markActivePeer();
  loadMessages(true);
}

function selectPeer(userId, username){
  selectedScope = "dialog";
  selectedPeer  = userId;
  setTopic("💬 Chat with: " + username);
  markActivePeer();
  loadMessages(true);
}

// ---------- Messages ----------
async function loadMessages(forceScroll=false){
  if(!currentUser) return;
  let url = SERVER + "/messages?limit=200";
  if(selectedScope === "global"){
    url += "&scope=global";
  } else {
    url += "&scope=dialog&user_id=" + encodeURIComponent(currentUser.user_id) +
           "&peer_id=" + encodeURIComponent(selectedPeer);
  }

  const r = await fetch(url);
  if(!r.ok) return;
  const list = await r.json();
  const box = document.getElementById("messages");
  const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 20;

  box.innerHTML = "";
  list.forEach(m=>{
    const who = (m.sender_id === currentUser.user_id) ? "You" : (m.sender_name || m.sender_id);
    const line = el("div", "line" + (who==="You" ? " me" : ""), `${who}: ${m.text}`);
    box.appendChild(line);
  });

  if(forceScroll || atBottom){
    box.scrollTop = box.scrollHeight;
  }
}

document.getElementById("inputForm").onsubmit = async (e)=>{
  e.preventDefault();
  if(!currentUser) return;
  const inp = document.getElementById("messageInput");
  const text = inp.value.trim();
  if(!text) return;
  const payload = {
    sender_id: currentUser.user_id,
    recipient: (selectedScope==="global" ? "all" : selectedPeer),
    text
  };
  await fetch(SERVER+"/send", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  inp.value = "";
  loadMessages(true);
};

// ---------- Polling ----------
function startPolling(){
  stopPolling();
  pollTimer = setInterval(()=>{
    loadMessages(false);
    refreshUsers();
  }, 1500);
}
function stopPolling(){
  if(pollTimer){ clearInterval(pollTimer); pollTimer = null; }
}

// ---------- Admin ----------
async function adminLogin(){
  const pwd = document.getElementById("adminPwd").value;
  const r = await fetch(SERVER+"/admin/login",{
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({password: pwd})
  });
  const d = await r.json();
  if(d.error){ alert(d.error); return; }
  adminPwd = pwd;
  loadAdmin();
}

async function loadAdmin(){
  const r = await fetch(SERVER+"/admin/users?password="+encodeURIComponent(adminPwd));
  const d = await r.json();
  if(d.error){ alert(d.error); return; }
  let html = "<h3>Admin Panel</h3><div class='toolbar'>"+
             "<button onclick='resetDB()'>Reset DB</button></div><ul>";
  d.users.forEach(u=>{
    html += `<li>${u.username} — messages: ${u.messages}</li>`;
  });
  html += "</ul>";
  document.getElementById("adminForm").innerHTML = html;
}

async function resetDB(){
  const r = await fetch(SERVER+"/admin/reset",{
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({password: adminPwd})
  });
  const d = await r.json();
  alert(JSON.stringify(d));
  loadAdmin();
}

// ---------- Header buttons ----------
document.getElementById("loginBtn").onclick = showLogin;
document.getElementById("adminBtn").onclick = showAdmin;
document.getElementById("logoutBtn").onclick = doLogout;

// старт
showLogin();
</script>
</body>
</html>
