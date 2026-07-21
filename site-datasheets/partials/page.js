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
// Die stack: buttons always work; pointer rotation is a progressive enhancement.
(function(){
  var die=document.querySelector('.die');
  if(!die)return;
  var motionQuery=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)');
  var reduce=!!(motionQuery&&motionQuery.matches);
  var printQuery=window.matchMedia&&window.matchMedia('print');
  var pointerEnabled=!reduce;
  var stack=die.querySelector('.die-3d');
  var panel=document.getElementById('die-panel');
  var instruction=die.parentElement&&die.parentElement.querySelector('.die-instruction');
  var faces=Array.prototype.slice.call(die.querySelectorAll('.die-face'));
  if(!stack||!panel||!faces.length)return;

  document.documentElement.classList.add(reduce?'js-static':'js-3d');
  var promptMarkup=panel.innerHTML;
  var suppressClickUntil=0;
  var selectedFace=null;

  function syncInstruction(){
    if(!instruction)return;
    var staticView=!pointerEnabled||(motionQuery&&motionQuery.matches)||
      (printQuery&&printQuery.matches);
    instruction.textContent=staticView?
      'functional block stack · static overview':
      'functional block stack · drag to rotate · select a layer';
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
    btn.addEventListener('click',function(e){
      if(Date.now()<suppressClickUntil){
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      open(btn);
    });
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

  if(reduce)return; // Static SVG + flat buttons remain available above.

  var DRAG_THRESHOLD=7;
  var pointerId=null;
  var startX=0;
  var startY=0;
  var startRotateX=62;
  var startRotateZ=-28;
  var rotationX=startRotateX;
  var rotationZ=startRotateZ;
  var dragged=false;
  var startedOnFace=false;

  function clamp(value,min,max){return Math.max(min,Math.min(max,value));}
  function applyRotation(){
    stack.style.setProperty('--die-rotate-x',rotationX.toFixed(2)+'deg');
    stack.style.setProperty('--die-rotate-z',rotationZ.toFixed(2)+'deg');
  }
  stack.addEventListener('pointerdown',function(e){
    if(e.isPrimary===false||(e.pointerType==='mouse'&&e.button!==0))return;
    pointerId=e.pointerId;
    startX=e.clientX;
    startY=e.clientY;
    startRotateX=rotationX;
    startRotateZ=rotationZ;
    dragged=false;
    startedOnFace=!!(e.target.closest&&e.target.closest('.die-face'));
  });
  stack.addEventListener('pointermove',function(e){
    if(e.pointerId!==pointerId)return;
    var dx=e.clientX-startX;
    var dy=e.clientY-startY;
    if(!dragged){
      if(Math.hypot(dx,dy)<DRAG_THRESHOLD)return;
      dragged=true;
      if(stack.setPointerCapture)stack.setPointerCapture(pointerId);
      stack.classList.add('is-dragging');
    }
    e.preventDefault();
    rotationX=clamp(startRotateX-dy*.12,55,70);
    rotationZ=clamp(startRotateZ+dx*.18,-35,35);
    applyRotation();
  });
  function finishPointer(e,blockClick){
    if(e.pointerId!==pointerId)return;
    if(blockClick&&dragged&&startedOnFace)suppressClickUntil=Date.now()+300;
    stack.classList.remove('is-dragging');
    if(stack.hasPointerCapture&&stack.hasPointerCapture(pointerId))stack.releasePointerCapture(pointerId);
    pointerId=null;
    dragged=false;
    startedOnFace=false;
  }
  stack.addEventListener('pointerup',function(e){finishPointer(e,true);});
  stack.addEventListener('pointercancel',function(e){finishPointer(e,false);});
})();
