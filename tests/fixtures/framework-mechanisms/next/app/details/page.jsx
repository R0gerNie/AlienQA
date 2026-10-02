'use client';
export default function Details(){return <main><h1>Details</h1><p>Summary</p><button onClick={()=>setTimeout(()=>{throw new TypeError('T05 framework detail handler unavailable')},20)}>Trigger fault</button></main>}
