

const CONFIG={
		githubUser:'Zpd8x',
		repository:'SDM',
		version:'v2.0.0'
	};
	
	
const releaseBase=()=>`https://github.com/${CONFIG.githubUser}/${CONFIG.repository}/releases/download/${CONFIG.version}`;
const assets={setup:'SDM_v2.0.0_Setup_x64.exe',portable:'SDM_v2.0.0_Portable_x64.zip',extension:'SDM_Browser_Extension_v2.0.0.zip',checksums:'SHA256SUMS.txt'};
document.querySelectorAll('[data-release]').forEach(a=>{const key=a.dataset.release;a.href=`${releaseBase()}/${assets[key]}`});
document.querySelectorAll('[data-repo]').forEach(a=>a.href=`https://github.com/${CONFIG.githubUser}/${CONFIG.repository}`);
const menu=document.querySelector('.menu-btn'),links=document.querySelector('.nav-links');menu?.addEventListener('click',()=>links.classList.toggle('open'));

document.querySelectorAll('.copy').forEach(btn=>btn.addEventListener('click',async()=>{const pre=btn.parentElement.querySelector('code');await navigator.clipboard.writeText(pre.innerText);btn.textContent='Copied';setTimeout(()=>btn.textContent='Copy',1400)}));
document.querySelectorAll('[data-year]').forEach(e=>e.textContent=new Date().getFullYear());
