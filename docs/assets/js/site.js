const CONFIG={githubUser:'Zpd8x',repository:'SDM',version:'v2.0.0'};
const releaseBase=()=>`https://github.com/${CONFIG.githubUser}/${CONFIG.repository}/releases/download/${CONFIG.version}`;
const assets={setup:'SDM_v2.0.0_Setup_x64.exe',portable:'SDM_v2.0.0_Portable_x64.zip',extension:'SDM_Browser_Extension_v2.0.0.zip',checksums:'SHA256SUMS.txt'};
document.querySelectorAll('[data-release]').forEach(link=>{const key=link.dataset.release;if(assets[key])link.href=`${releaseBase()}/${assets[key]}`});
document.querySelectorAll('[data-repo]').forEach(link=>link.href=`https://github.com/${CONFIG.githubUser}/${CONFIG.repository}`);
document.querySelectorAll('[data-releases]').forEach(link=>link.href=`https://github.com/${CONFIG.githubUser}/${CONFIG.repository}/releases`);
document.querySelectorAll('[data-issues]').forEach(link=>link.href=`https://github.com/${CONFIG.githubUser}/${CONFIG.repository}/issues`);
document.querySelectorAll('[data-year]').forEach(node=>node.textContent=new Date().getFullYear());
const menu=document.querySelector('.menu-btn'),nav=document.querySelector('.nav-links');
menu?.addEventListener('click',()=>{const open=nav.classList.toggle('open');menu.setAttribute('aria-expanded',String(open))});
document.addEventListener('click',event=>{if(nav?.classList.contains('open')&&!event.target.closest('.nav-inner')){nav.classList.remove('open');menu?.setAttribute('aria-expanded','false')}});
const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){const delay=Number(entry.target.dataset.delay||0);setTimeout(()=>entry.target.classList.add('visible'),delay);observer.unobserve(entry.target)}}),{threshold:.12});
document.querySelectorAll('.reveal').forEach(el=>observer.observe(el));
const parallax=document.querySelector('[data-parallax]');
if(parallax&&matchMedia('(pointer:fine)').matches&&!matchMedia('(prefers-reduced-motion:reduce)').matches){const stage=parallax.closest('.product-stage');stage.addEventListener('mousemove',event=>{const r=stage.getBoundingClientRect(),x=(event.clientX-r.left)/r.width-.5,y=(event.clientY-r.top)/r.height-.5;parallax.style.transform=`rotateY(${x*9-5}deg) rotateX(${-y*7+2}deg) translate3d(${x*5}px,${y*5}px,0)`});stage.addEventListener('mouseleave',()=>parallax.style.transform='rotateY(-5deg) rotateX(2deg)')}
document.querySelectorAll('.copy').forEach(btn=>btn.addEventListener('click',async()=>{const code=btn.parentElement.querySelector('code');if(!code)return;await navigator.clipboard.writeText(code.innerText);btn.textContent='Copied';setTimeout(()=>btn.textContent='Copy',1400)}));
