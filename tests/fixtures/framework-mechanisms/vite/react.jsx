import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {createPortal} from 'react-dom';
function App(){
 const [value,setValue]=useState(''),[checked,setChecked]=useState(false),[message,setMessage]=useState(''),[open,setOpen]=useState(false),[busy,setBusy]=useState(false);
 const mode=new URLSearchParams(location.search).get('mode');
 return <main aria-busy={busy}><h1>Profile</h1><form id="profile" onSubmit={e=>{e.preventDefault();setBusy(true);setTimeout(()=>{setBusy(false);if(mode!=='missing')setMessage('Saved '+value)},700)}}>
 <label>Email<input type="email" required value={value} onChange={e=>setValue(mode==='reset'?'':e.target.value)} onBlur={()=>setChecked(true)}/></label>
 <output>{checked?'Email checked':''}</output><button>Save</button></form><p role="status">{message}</p>
 <button onClick={()=>setOpen(true)}>Open dialog</button>{open&&createPortal(<div role="dialog" aria-modal="true" aria-label="Confirm"><p>Confirm settings</p><button onClick={()=>setOpen(false)}>Close</button></div>,document.body)}
 <button onClick={()=>{history.pushState({},'',location.pathname+location.search+'#details');setMessage('Details')}}>Details</button>
 <button disabled={message!=='Details'} onClick={()=>setTimeout(()=>{throw new TypeError('T05 framework detail handler unavailable')},20)}>Trigger fault</button></main>
}
createRoot(document.getElementById('root')).render(<App/>);
