// Motion upgrade: swap a poster for silent video only when motion is welcome.
(function(){
  var motionQuery=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)');
  if(motionQuery&&motionQuery.matches)return;
  if(!('IntersectionObserver' in window))return;
  document.querySelectorAll('img[data-video]').forEach(function(img){
    var io=new IntersectionObserver(function(es){es.forEach(function(e){
      if(!e.isIntersecting)return;
      // The preference can change after the observer was registered.
      if(motionQuery&&motionQuery.matches){io.unobserve(img);return;}
      io.unobserve(img);
      var v=document.createElement('video');
      var media=document.createElement('span');
      media.className='motion-media';
      v.muted=true;v.defaultMuted=true;v.loop=true;v.autoplay=true;v.playsInline=true;v.controls=true;
      v.setAttribute('muted','');v.setAttribute('playsinline','');v.setAttribute('autoplay','');v.setAttribute('loop','');v.setAttribute('controls','');v.setAttribute('preload','auto');
      v.poster=img.currentSrc||img.src;v.src=img.getAttribute('data-video');
      v.setAttribute('aria-label',img.alt);
      v.style.width='100%';v.style.height='auto';v.style.display='block';v.style.border='1px solid #e0e0e0';
      img.replaceWith(media);media.appendChild(img);media.appendChild(v);
      function playVideo(){var p=v.play();if(p&&p.catch)p.catch(function(){});}
      function syncMotion(e){if(e.matches){v.pause();}else{playVideo();}}
      if(motionQuery){
        if(motionQuery.addEventListener)motionQuery.addEventListener('change',syncMotion);
        else if(motionQuery.addListener)motionQuery.addListener(syncMotion);
      }
      playVideo();
    });},{rootMargin:'120px'});
    io.observe(img);
  });
})();
// copy-to-clipboard for instruction rows
document.querySelectorAll('.copybtn').forEach(function(b){
  b.addEventListener('click',function(){
    var t=b.getAttribute('data-copy')||'';
    if(navigator.clipboard){navigator.clipboard.writeText(t).then(function(){
      var old=b.textContent;b.textContent='copied';setTimeout(function(){b.textContent=old;},1200);
    }).catch(function(){});}
  });
});
// Die stack: the isometric SVG is the visual; each layer is a focusable card that opens its detail.
(function(){
  var die=document.querySelector('.die');
  if(!die)return;
  var motionQuery=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)');
  var printQuery=window.matchMedia&&window.matchMedia('print');
  var stack=die.querySelector('.die-3d');
  var panel=document.getElementById('die-panel');
  var instruction=die.parentElement&&die.parentElement.querySelector('.die-instruction');
  var faces=Array.prototype.slice.call(die.querySelectorAll('.die-face'));
  if(!stack||!panel||!faces.length)return;

  document.documentElement.classList.add('js-die');
  var promptMarkup=panel.innerHTML;
  var selectedFace=null;

  function syncInstruction(){
    if(!instruction)return;
    instruction.textContent='functional block stack · select a layer for detail';
  }
  [motionQuery,printQuery].forEach(function(query){
    if(!query)return;
    if(query.addEventListener)query.addEventListener('change',syncInstruction);
    else if(query.addListener)query.addListener(syncInstruction);
  });
  syncInstruction();

  function setUnpressed(){
    faces.forEach(function(face){
      face.setAttribute('aria-pressed','false');
      face.setAttribute('aria-expanded','false');
    });
  }
  function addDetail(label,value){
    var p=document.createElement('p');
    var strong=document.createElement('strong');
    strong.textContent=label+' ';
    p.appendChild(strong);
    p.appendChild(document.createTextNode(value||''));
    panel.appendChild(p);
  }
  function githubSource(raw){
    try{
      var url=new URL(raw,window.location.href);
      if(url.protocol==='https:'&&url.hostname==='github.com')return url.href;
    }catch(error){}
    return '';
  }
  function open(btn){
    setUnpressed();
    btn.setAttribute('aria-pressed','true');
    btn.setAttribute('aria-expanded','true');
    selectedFace=btn;
    while(panel.firstChild)panel.removeChild(panel.firstChild);
    var heading=document.createElement('h3');
    heading.textContent=btn.textContent;
    panel.appendChild(heading);
    addDetail('Plain terms.',btn.getAttribute('data-plain'));
    addDetail('Engineering.',btn.getAttribute('data-eng'));
    var src=githubSource(btn.getAttribute('data-src'));
    if(src){
      var sourceLine=document.createElement('p');
      var sourceLink=document.createElement('a');
      sourceLink.href=src;
      sourceLink.target='_blank';
      sourceLink.rel='noopener';
      sourceLink.textContent='Source on GitHub';
      sourceLine.appendChild(sourceLink);
      panel.appendChild(sourceLine);
    }
  }
  function clearSelection(){
    var returnFocus=selectedFace;
    var focusWasInPanel=panel.contains(document.activeElement);
    setUnpressed();
    selectedFace=null;
    panel.innerHTML=promptMarkup;
    if(focusWasInPanel&&returnFocus)returnFocus.focus();
  }

  faces.forEach(function(btn){
    btn.setAttribute('aria-pressed','false');
    btn.addEventListener('click',function(){open(btn);});
  });

  die.addEventListener('keydown',function(e){
    if(e.key==='Escape'){
      e.preventDefault();
      clearSelection();
      return;
    }
    var btn=e.target.closest&&e.target.closest('.die-face');
    if(!btn||!die.contains(btn))return;
    if(e.key==='Enter'||e.key===' '){
      e.preventDefault();
      open(btn);
    }
  });
})();
