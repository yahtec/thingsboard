self.onInit = function(){};
self.onDataUpdated = function(){
  var $c = self.ctx.$container;
  var host = $c.find('.pt-host');
  if (!host.length) return;

  function stateParams(){
    try {
      var raw = new URL(window.location.href).searchParams.get('state');
      if (!raw) return {};
      var arr = JSON.parse(atob(decodeURIComponent(raw)));
      for (var i = arr.length - 1; i >= 0; i--){
        if (arr[i] && arr[i].params) return arr[i].params;
      }
    } catch(e){}
    return {};
  }

  var n = parseInt(stateParams().hpIndex || stateParams().hp || 1) || 1;
  host.html('<div class="pt-title">PAC Hybride N' + n + '</div>');
};

self.typeParameters = function(){
  return { maxDatasources: 1, maxDataKeys: 1, singleEntity: true };
};
self.onResize = function(){};
self.onDestroy = function(){};
