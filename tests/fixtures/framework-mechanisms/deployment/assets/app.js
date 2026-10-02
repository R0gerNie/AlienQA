document.querySelector('#save').onclick=()=>{document.querySelector('[role=status]').textContent='Saved '+document.querySelector('#name').value};
document.querySelector('#fault').onclick=()=>{throw new TypeError('T01 mounted handler unavailable')};
