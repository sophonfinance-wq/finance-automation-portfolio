// Motion upgrade: swap a poster for silent video only when motion is welcome.
(function(){
  var motionQuery=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)');
  if(motionQuery&&motionQuery.matches)return;
  if(!('IntersectionObserver' in window))return;
  function playFilm(v){var p=v.play();if(p&&p.catch)p.catch(function(){});}
  // Films prepared off-document, still waiting to prove a frame (see placeFilm).
  // Some phones (iOS Low Power Mode, data saver) gate the first muted autoplay
  // until any interaction, so retry on early gestures and when the tab comes back.
  // Only pending films are retried: a film already on the page carries a control
  // bar, and replaying it would overrule a visitor who pressed pause.
  var pending=[];
  function retryPending(){pending.slice().forEach(playFilm);}
  ['touchstart','pointerdown','click','keydown'].forEach(function(evt){
    window.addEventListener(evt,retryPending,{passive:true});
  });
  document.addEventListener('visibilitychange',function(){if(!document.hidden)retryPending();});
  document.querySelectorAll('img[data-video]').forEach(function(img){
    var io=new IntersectionObserver(function(es){es.forEach(function(e){
      if(!e.isIntersecting)return;
      // The preference can change after the observer was registered.
      if(motionQuery&&motionQuery.matches){io.unobserve(img);return;}
      io.unobserve(img);
      // Only upgrade to <video> when data-video is genuinely a video. A spec whose
      // media.motion falls back to its poster would otherwise give a <video> with an
      // SVG src that no browser can decode -- and .motion-media>img{display:none}
      // hides the working image, leaving a control bar over a diagram that can never
      // play. Belt and braces: the generator also stops emitting the attribute.
      var msrc=img.getAttribute('data-video')||'';
      if(!/\.(mp4|webm|ogv)$/i.test(msrc))return;
      var v=document.createElement('video');
      var media=document.createElement('span');
      media.className='motion-media';
      v.muted=true;v.defaultMuted=true;v.loop=true;v.autoplay=true;v.playsInline=true;v.controls=true;
      v.setAttribute('muted','');v.setAttribute('playsinline','');v.setAttribute('autoplay','');v.setAttribute('loop','');v.setAttribute('controls','');v.setAttribute('preload','auto');
      v.poster=img.currentSrc||img.src;v.src=img.getAttribute('data-video');
      v.setAttribute('aria-label',img.alt);
      v.style.width='100%';v.style.height='auto';v.style.display='block';v.style.border='1px solid #e0e0e0';
      // The film does not take the still's place until it proves it can render.
      // Media-gating in-app webviews (Facebook's iOS browser among them) admit
      // play() but hold back the data or the decode, and .motion-media>img hides
      // the still the instant the wrapper goes in -- so a film swapped in on faith
      // painted nothing and the figure went blank where a good still used to be.
      // The still therefore holds its ground while the film is prepared
      // off-document, and only its first 'playing' frame -- actual pixels flowing
      // -- earns the wrapper. A film that errors, or never clears the gate, never
      // swaps in at all, and the reader keeps the diagram either way.
      pending.push(v);
      function drop(){var i=pending.indexOf(v);if(i>-1)pending.splice(i,1);}
      var placed=false;
      function placeFilm(){
        if(placed)return;
        // A preference for less motion can arrive while the film is still pending;
        // leave it off-document and let the still stand.
        if(motionQuery&&motionQuery.matches)return;
        placed=true;drop();
        img.replaceWith(media);media.appendChild(img);media.appendChild(v);
        // Now that the film is in the page, ask it to run there: a film held
        // off-document gets no autoplay of its own and the browser may suspend
        // it once it has proven its frame, so the visible element starts here.
        playFilm(v);
      }
      v.addEventListener('playing',placeFilm);
      v.addEventListener('error',drop);
      // A play() issued while the resource is still loading is aborted by that
      // same load, and an off-document film has no autoplay to fall back on --
      // so ask again the moment there is actually data to play.
      v.addEventListener('loadeddata',function(){playFilm(v);});
      v.addEventListener('canplay',function(){playFilm(v);});
      function syncMotion(e){if(e.matches){v.pause();}else{playFilm(v);}}
      if(motionQuery){
        if(motionQuery.addEventListener)motionQuery.addEventListener('change',syncMotion);
        else if(motionQuery.addListener)motionQuery.addListener(syncMotion);
      }
      playFilm(v);
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
