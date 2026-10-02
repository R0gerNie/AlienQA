"""DOM-only observable metadata; no framework objects or event-handler inspection."""

INTERACTIVE = ("button, a[href], input, select, textarea, [role='button'], [role='link'], "
               "[role='combobox'], [role='listbox'], [role='option'], [role='checkbox'], "
               "[role='radio'], [role='switch'], [role='tab'], [role='menuitem'], "
               "[contenteditable='true'], [title], [data-tooltip], [aria-haspopup]")

HELPERS = r"""
const visible = el => el.getClientRects().length > 0 &&
    getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none';
const nameOf = el => {
    const refs = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    const referenced = refs.map(id => el.getRootNode().getElementById?.(id)?.textContent || '').join(' ').trim();
    return (referenced || el.getAttribute('aria-label') ||
        (el.labels && [...el.labels].map(l => l.innerText).join(' ')) ||
        (['INPUT','TEXTAREA','SELECT'].includes(el.tagName) ? el.placeholder ||
            (['submit','button'].includes(el.type) ? el.value : '') : el.innerText || el.textContent) || '').trim().replace(/\s+/g, ' ');
};
const roleOf = el => el.getAttribute('role') || ({BUTTON:'button', A: el.hasAttribute('href') ? 'link' : '',
    SELECT:el.multiple?'listbox':'combobox', TEXTAREA:'textbox', INPUT:
    ({checkbox:'checkbox',radio:'radio',button:'button',submit:'button',number:'spinbutton',range:'slider'}[el.type] || 'textbox')})[el.tagName] || '';
const selectorOf = el => {
    if (el.id) return '#' + CSS.escape(el.id);
    for (const attr of ['data-testid','data-view','name']) {
        const value = el.getAttribute(attr);
        if (value) {
            const candidate = el.tagName.toLowerCase() + '[' + attr + '=' + JSON.stringify(value) + ']';
            if (el.getRootNode().querySelectorAll(candidate).length === 1) return candidate;
        }
    }
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1) {
        if (node.id) {parts.unshift('#'+CSS.escape(node.id)); break;}
        let part = node.tagName.toLowerCase();
        const siblings = node.parentElement ? [...node.parentElement.children].filter(x=>x.tagName===node.tagName) : [];
        if (siblings.length > 1) part += ':nth-of-type('+(siblings.indexOf(node)+1)+')';
        parts.unshift(part); node = node.parentElement;
    }
    return parts.join(' > ');
};
const scopeOf = el => {
    const parent = el.closest('[role="dialog"],dialog,form,[role="listbox"],[role="menu"]');
    return parent && parent !== el ? selectorOf(parent) : '';
};
"""

METADATA = "el => {" + HELPERS + r"""
const form = el.form || el.closest('form');
return {
    selector: selectorOf(el), scope: scopeOf(el), name: nameOf(el), role: roleOf(el),
    label: (el.labels && [...el.labels].map(l=>l.innerText).join(' ')) || el.getAttribute('aria-label') || '',
    placeholder: el.placeholder || '', tag: el.tagName.toLowerCase(), text: nameOf(el),
    href: el.getAttribute('href') || '', input_type: el.type || 'text',
    value: el.value || (el.isContentEditable ? el.textContent : ''),
    disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true', readonly: !!el.readOnly,
    checked: !!el.checked || el.getAttribute('aria-checked') === 'true', required: !!el.required,
    selected: el.getAttribute('aria-selected') === 'true', expanded: el.getAttribute('aria-expanded'),
    focused: el.getRootNode().activeElement === el, visible: visible(el),
    group_checked: el.type === 'radio' && !!el.name && [...(form ? form.elements : document.querySelectorAll('input'))]
        .some(other=>other.type==='radio' && other.name===el.name && other.checked),
    contenteditable: !!el.isContentEditable, min: el.min || '', max: el.max || '', step: el.step || '',
    pattern: el.pattern || '', maxlength: el.maxLength >= 0 ? el.maxLength : null,
    form_key: form ? selectorOf(form) : '',
    implicit_submit: !!form && !form.querySelector('button:not([type]),button[type="submit"],input[type="submit"]'),
    hover_hint: !!(el.title || el.getAttribute('data-tooltip') || el.getAttribute('aria-haspopup')),
    options: el.tagName === 'SELECT' ? [...el.options].map(o=>({value:o.value,label:o.text,disabled:o.disabled,selected:o.selected})) : []
};
}"""

FORM_STATE = "elements => {" + HELPERS + r"""
const rows = elements.filter(visible).map((el,index)=>{
    const semantic = nameOf(el);
    const identity = el.id || el.getAttribute('data-testid') || el.name || semantic;
    return {key:scopeOf(el)+'|'+roleOf(el)+'|'+(identity || 'index:'+index),
        type:el.type || el.tagName.toLowerCase(),
        value:['INPUT','TEXTAREA','SELECT'].includes(el.tagName) ? el.value : el.isContentEditable ? el.textContent : null,
        checked:!!el.checked || el.getAttribute('aria-checked') === 'true',
        disabled:!!el.disabled || el.getAttribute('aria-disabled')==='true', readonly:!!el.readOnly,
        expanded:el.getAttribute('aria-expanded'), selected:el.getAttribute('aria-selected'),
        busy:el.getAttribute('aria-busy'), modal:el.getAttribute('aria-modal'), open:el.tagName==='DIALOG'?el.open:null};
});
return rows.sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
}"""

SETTLE_STATE = "() => {" + HELPERS + r"""
const busy = [...document.querySelectorAll('[aria-busy="true"],[role="progressbar"]')].filter(visible).length;
return {url:location.href, text:(document.body?.innerText || '').slice(0,8000), pending:busy>0,
    controls:[...document.querySelectorAll('input,textarea,select,button,[aria-expanded],[aria-selected],[role="dialog"],dialog')]
        .filter(visible).slice(0,200).map(el=>[nameOf(el),el.value,!!el.disabled,el.getAttribute('aria-expanded'),el.getAttribute('aria-selected')])};
}"""

COVERAGE = "() => {" + HELPERS + r"""
let openRoots = 0;
const walk = root => {for(const el of root.querySelectorAll('*')) if(el.shadowRoot){openRoots++;walk(el.shadowRoot);}};
walk(document);
return {frames:[...document.querySelectorAll('iframe,frame')].map(el=>({selector:selectorOf(el),status:'unvisited'})),
    shadow:{open_roots:openRoots,status:'unverified',note:'open shadow enumeration/state/replay is unverified; closed roots cannot be detected reliably'}};
}"""
