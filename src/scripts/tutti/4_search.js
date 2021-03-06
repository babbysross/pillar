/*
* == Search ==
* index and algolia settings are defined in layout.pug
*/

var elasticSearcher = (function() {

  var deze = {

    query:"",
    project_id:"",
    url:"",
    newhits: [],
    terms: {},
    page: 0,
    last_query: null,  // to prevent re-querying for the same thing.

    setQuery: (function(q, _url){
      deze.query=q;
      if (_url !== undefined) {
        deze.url=_url;
      }
    }),

    setProjectID: (function(pid){
      deze.project_id = pid;
    }),

    setCurrentPage: (function(page){
      if(page === undefined){
        return;
      }
      deze.page = page;
    }),

    //result callback
    results: (function(content){}),

    //error callback
    error: (function(message){
      toastr.error(message);
    }),

    on: (function(type, callback){
      deze[type] = callback;
    }),

    //parse the agg stuff
    aggs: (function(data){
      return deze.newhits.aggregations;
    }),

    toggleTerm: (function(term, value){
      if (deze.terms[term] !== undefined) {
        delete deze.terms[term];
      } else {
        deze.terms[term] = value;
      }
    }),

    isRefined: (function(term, value){
      if (deze.terms[term] === value) {
        return true;
      }
      return false;
    }),

    //get response from elastic and rebuild json
    //so we  can be a drop in of angolia
    execute: (function(){
      params = {
        q: deze.query,
        page: deze.page,
        project: deze.project_id,
      };
      //add term filters
      Object.assign(params, deze.terms);

      var pstr = jQuery.param( params );
      if (pstr === deze.last_query) return;

      $.getJSON("/api/newsearch" + deze.url + "?"+ pstr)
      .done(function (data) {
        var hits = data.hits.hits;
        var newhits = hits.map(function(hit){
          return hit._source;
        });

        deze.newhits = newhits.slice(0);
        //cb(newhits.slice(0));
        deze.last_query = pstr;
        deze.results({
          'count': data.hits.total,
          'hits': newhits.slice(0),
          'took': data.took,
          'page': deze.page,
          'aggs': data.aggregations,
        });
      })
      .fail(function(err) {
          toastr.error(xhrErrorResponseMessage(err), 'Unable to perform search:');
          deze.last_query = null;
      })
      ;

    })

  };

  return {
    execute: deze.execute,
    on: deze.on,
    setQuery: deze.setQuery,
    setProjectID: deze.setProjectID,
    setCurrentPage: deze.setCurrentPage,
    query: deze.query,
    page: deze.page,
    toggleTerm: deze.toggleTerm,
    isRefined: deze.isRefined,
  };

})();


var elasticSearch = (function($, url) {
  return function findMatches(q, cb, async){
    if (!cb) { return; }
    $.fn.getSearch(q, cb, async, url);
  };
});



(function( $ ){

  $.fn.getSearch = function(q, cb, async, url){

    var newhits = [];
    if(url === undefined){
      url = '';
    }

    $.getJSON("/api/newsearch" + url + "?q=" + q, function( data ) {
      var hits = data.hits.hits;
      newhits = hits.map(function(hit){
        return hit._source;
      });
      cb(newhits.slice(0));
      if(async !== undefined){
        async(newhits.slice(0));
      }
    });
  };


}(jQuery));


$(document).ready(function() {

  var searchInput = $('#cloud-search');
  if (!searchInput.length) return;

  var tu = searchInput.typeahead({hint: true}, {
    //source: algoliaIndex.ttAdapter(),
    source: elasticSearch($),
    async: true,
    displayKey: 'name',
    limit: 9,  //  Above 10 it stops working from
               //  some magic reason
    minLength: 0,
    templates: {
      suggestion: function(hit) {
        var hitFree = (hit.is_free ? '<div class="search-hit-ribbon"><span>free</span></div>' : '');
        var hitPicture;

        if (hit.picture){
          hitPicture = '<img src="' + hit.picture + '"/>';
        } else {
          hitPicture = '<div class="search-hit-thumbnail-icon">';
          hitPicture += (hit.media ? '<i class="pi-' + hit.media + '"></i>' : '<i class="dark pi-'+ hit.node_type + '"></i>');
          hitPicture += '</div>';
        }
        var $span = $('<span>').addClass('project').text(hit.project.name);
        var $searchHitName = $('<div>').addClass('search-hit-name')
          .attr('title', hit.name)
          .text(hit.name);

        const $nodeType = $('<span>').addClass('node_type').text(hit.node_type);
        const hitMedia = (hit.media ? ' · ' + $('<span>').addClass('media').text(hit.media)[0].outerHTML : '');

        return $('<a/>', {
              href: '/nodes/'+ hit.objectID + '/redir',
              class: "search-site-result",
              id: hit.objectID
           }).append(
             '<div class="search-hit">' +
               '<div class="search-hit-thumbnail">' +
                 hitPicture +
                 hitFree +
               '</div>' +
               $searchHitName.html() +
               '<div class="search-hit-meta">' +
                 $span.html() + ' · ' +
                 $nodeType.html() +
                 hitMedia +
               '</div>' +
             '</div>'
          )
      }
    }
  });

  $('.search-site-result.advanced, .search-icon').on('click', function(e){
    e.stopPropagation();
    e.preventDefault();
    window.location.href = '/search?q='+ $("#cloud-search").val() + '&page=1';
  });


  searchInput.bind('typeahead:select', function(ev, hit) {
    $('.search-icon').removeClass('pi-search').addClass('pi-spin spin');

    window.location.href = '/nodes/'+ hit.objectID + '/redir';
  });

  searchInput.bind('typeahead:active', function() {
    $('#search-overlay').addClass('active');
    $('.page-body').addClass('blur');
  });

  searchInput.bind('typeahead:close', function() {
    $('#search-overlay').removeClass('active');
    $('.page-body').removeClass('blur');
  });

  searchInput.keyup(function(e) {
    if ( $('.tt-dataset').is(':empty') ){
      if(e.keyCode == 13){
        window.location.href = '/search#q='+ $("#cloud-search").val() + '&page=1';
      }
    }
  });

  searchInput.bind('typeahead:render', function(event, suggestions, async, dataset) {
    if( suggestions != undefined && $('.tt-all-results').length <= 0){
      $('.tt-dataset').append(
        $("<a/>", {
           id: "search-advanced",
           href: '/search?q='+ $("#cloud-search").val() + '&page=1',
           class: "search-site-result advanced tt-suggestion",
        }).append(
          '<div class="search-hit">' +
            '<div class="search-hit-thumbnail">' +
              '<div class="search-hit-thumbnail-icon">' +
                '<i class="pi-search"></i>' +
              '</div>' +
            '</div>' +
            '<div class="search-hit-name">' +
              'Use Advanced Search' +
            '</div>' +
          '</div>'
        )
      );
    }
  });

});
