import {createApp} from 'vue/dist/vue.esm-bundler.js';
createApp({data:()=>({email:'',message:'',checked:false,expanded:false,country:'',busy:false,mode:new URLSearchParams(location.search).get('mode')}),
 methods:{fault(){setTimeout(()=>{throw new TypeError('T05 framework detail handler unavailable')},20)},details(){history.pushState({},'',location.pathname+location.search+'#details');this.message='Details'},save(){this.busy=true;setTimeout(()=>{this.busy=false;if(this.mode!=='missing')this.message='Saved '+this.email},700)},choose(){if(this.mode!=='option-fails')this.country='China';this.expanded=false}},
 template:`<main :aria-busy="busy"><h1>Profile</h1><form id="profile" @submit.prevent="save"><label>Email<input type="email" required v-model="email" @input="mode==='reset' && (email='')" @blur="checked=true"></label><output>{{checked?'Email checked':''}}</output><button>Save</button></form><p role="status">{{message}}</p>
 <div role="combobox" aria-label="Country" :aria-expanded="expanded" @click="expanded=!expanded">{{country || 'Country'}}</div>
 <div role="listbox" v-if="expanded"><div role="option" :aria-selected="country==='China'" @click="choose">China</div></div>
 <button @click="details">Details</button><button :disabled="message!=='Details'" @click="fault">Trigger fault</button></main>`
}).mount('#app');
