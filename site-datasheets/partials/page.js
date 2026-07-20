// motion upgrade: poster image swaps to its silent looping video when visible
document.querySelectorAll('img[data-video]').forEach(function(img){
  var io=new IntersectionObserver(function(es){es.forEach(function(e){
    if(!e.isIntersecting)return;io.unobserve(img);
    var v=document.createElement('video');
    v.muted=true;v.defaultMuted=true;v.loop=true;v.autoplay=true;v.playsInline=true;
    v.setAttribute('muted','');v.setAttribute('playsinline','');v.setAttribute('autoplay','');v.setAttribute('loop','');v.setAttribute('preload','auto');
    v.poster=img.currentSrc||img.src;v.src=img.getAttribute('data-video');
    v.setAttribute('role','img');v.setAttribute('aria-label',img.alt);
    v.style.width='100%';v.style.height='auto';v.style.display='block';v.style.border='1px solid #e0e0e0';
    img.replaceWith(v);var p=v.play();if(p&&p.catch)p.catch(function(){});
  });},{rootMargin:'120px'});
  io.observe(img);
});
// copy-to-clipboard for instruction rows
document.querySelectorAll('.copybtn').forEach(function(b){
  b.addEventListener('click',function(){
    var t=b.getAttribute('data-copy')||'';
    if(navigator.clipboard){navigator.clipboard.writeText(t).then(function(){
      var old=b.textContent;b.textContent='copied';setTimeout(function(){b.textContent=old;},1200);
    }).catch(function(){});}
  });
});
