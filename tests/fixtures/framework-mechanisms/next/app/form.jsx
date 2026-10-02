'use client';
import {useState,useEffect} from 'react';
import Link from 'next/link';
export default function Form(){
 const [ready,setReady]=useState(false),[value,setValue]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{const timer=setTimeout(()=>setReady(true),350);return ()=>clearTimeout(timer)},[]);
 return <section aria-busy={!ready||busy}><form id="profile" onSubmit={e=>{e.preventDefault();setBusy(true);setTimeout(()=>{setBusy(false);if(!new URLSearchParams(location.search).has('missing'))setMessage('Saved '+value)},700)}}>
 <label>Email<input type="email" required disabled={!ready} value={value} onChange={e=>setValue(e.target.value)}/></label><button disabled={!ready}>Save</button></form><p role="status">{message}</p><Link href="/details?tab=2#summary">Details</Link></section>
}
