
/* Reply */
$(document).on('click','body .comment-action-reply',function(e){
	e.preventDefault();

	// container of the comment we are replying to
	var parentDiv = $(this).closest('.comment-container');

	// container of the first-level comment in the thread
	var parentDivFirst = parentDiv.prevAll('.is-first:first');

	// Get the id of the comment
	if (parentDiv.hasClass('is-reply')) {
		parentNodeId = parentDivFirst.data('node-id');
	} else {
		parentNodeId = parentDiv.data('node-id');
	}
	if (!parentNodeId) {
		if (console) console.log('No parent ID found on ', parentDiv.toArray(), parentDivFirst.toArray());

		return;
	}

	// Get the textarea and set its parent_id data
	var commentField = document.getElementById('comment_field');
	commentField.dataset.originalParentId = commentField.dataset.parentId;
	commentField.dataset.parentId = parentNodeId;

	// Start the comment field with @authorname:
	var replyAuthor = parentDiv.find('.comment-author:first').html();

	$(commentField).val("**@" + replyAuthor + ":** ");

	// Add class for styling
	$('.comment-container').removeClass('is-replying');
	parentDiv.addClass('is-replying');

	// Move comment-reply container field after the parent container
	var commentForm = $('.comment-reply-container').detach();
	parentDiv.after(commentForm);
	// document.getElementById('comment_field').focus();
	$(commentField).focus();

	// Convert Markdown
	var convert = new Markdown.getSanitizingConverter().makeHtml;
	var preview = $('.comment-reply-preview-md');
	preview.html(convert($(commentField).val()));
	$('.comment-reply-field').addClass('filled');
});


/* Cancel Reply */
$(document).on('click','body .comment-action-cancel',function(e){
	e.preventDefault();

	$('.comment-reply-container').detach().prependTo('#comments-list');
	var commentField = document.getElementById('comment_field');
	commentField.dataset.parentId = commentField.dataset.originalParentId;
	delete commentField.dataset.originalParentId;

	$(commentField).val('');
	// Convert Markdown
	var convert = new Markdown.getSanitizingConverter().makeHtml;
	var preview = $('.comment-reply-preview-md');
	preview.html(convert($(commentField).val()));

	$('.comment-reply-field').removeClass('filled');
	$('.comment-container').removeClass('is-replying');
});


/* Rate */
$(document).on('click','body .comment-action-rating',function(e){
	e.preventDefault();

	var $this = $(this);
	var nodeId = $this.closest('.comment-container').data('node-id');
	var is_positive = !$this.hasClass('down');
	var parentDiv = $this.parent();
	var rated_positive = parentDiv.hasClass('positive');

	if (typeof nodeId === 'undefined') {
		if (console) console.log('Undefined node ID');
		return;
	}

	var op;
	if (parentDiv.hasClass('rated') && is_positive == rated_positive) {
		op = 'revoke';
	} else if (is_positive) {
		op = 'upvote';
	} else {
		op = 'downvote';
	}

	$.post("/nodes/comments/" + nodeId + "/rate/" + op)
	.done(function(data){

		// Add/remove styles for rated statuses
		switch(op) {
			case 'revoke':
				parentDiv.removeClass('rated');
				break;
			case 'upvote':
				parentDiv.addClass('rated');
				parentDiv.addClass('positive');
				break;
			case 'downvote':
				parentDiv.addClass('rated');
				parentDiv.removeClass('positive');
				break;
		}

		var rating = data['data']['rating_positive'] - data['data']['rating_negative'];
		$this.siblings('.comment-rating-value').text(rating);
	});
});

/**
 * Fetches a comment, returns a promise object.
 */
function loadComment(comment_id, projection)
{
	if (typeof comment_id === 'undefined') {
		console.log('Error, loadComment(', comment_id, ', ', projection, ') called.');
		return $.Deferred().reject();
	}

	// Add required projections for the permission system to work.
	projection.node_type = 1;
	projection.project = 1;

	var url = '/api/nodes/' + comment_id;
	return $.get({
		url: url,
		data: {projection: projection},
		cache: false,  // user should be ensured the latest comment to edit.
	});
}


function loadComments(commentsUrl)
{
	var commentsContainer = $('#comments-embed');

	return $.get(commentsUrl)
	.done(function(dataHtml) {
		// Update the DOM injecting the generate HTML into the page
		commentsContainer.html(dataHtml);
		$('body').trigger('pillar:comments-loaded');
	})
	.fail(function(xhr) {
		toastr.error('Could not load comments', xhr.responseText);

		commentsContainer.html('<a id="comments-reload"><i class="pi-refresh"></i> Reload comments</a>');
	});
}


/**
 * Shows an error in the "Post Comment" button.
 */
function show_comment_button_error(msg) {
	var $button = $('.comment-action-submit');
	var $textarea = $('#comment_field');

	$button.addClass('error');
	$textarea.addClass('error');
	$button.html(msg);

	setTimeout(function(){
		$button.html('<span><i class="pi-paper-plane"></i> Send</span>');
		$button.removeClass('error');
		$textarea.removeClass('error');
	}, 2500);
}


/**
 * Shows an error in the "edit comment" button.
 */
function show_comment_edit_button_error($button, msg) {
	var $textarea = $('#comment_field');

	$button.addClass('error');
	$textarea.addClass('field-error');
	$button.html(msg);

	setTimeout(function(){
		$button.html('<i class="pi-check"></i> Save Changes');
		$button.removeClass('button-field-error');
		$textarea.removeClass('field-error');
	}, 2500);
}


/**
 * Switches the comment to either 'edit' or 'view' mode.
 */
function comment_mode(clicked_item, mode)
{
	var $container = $(clicked_item).closest('.comment-container');
	var comment_id = $container.data('node-id');

	var $edit_buttons = $container.find('.comment-action-edit');

	if (mode == 'edit') {
		$edit_buttons.find('.edit_mode').hide();
		$edit_buttons.find('.edit_cancel').show();
		$edit_buttons.find('.edit_save').show();
	} else {
		$edit_buttons.find('.edit_mode').show();
		$edit_buttons.find('.edit_cancel').hide();
		$edit_buttons.find('.edit_save').hide();

		$container.find('.comment-body').removeClass('editing');
	}
}

/**
 * Return UI to normal, when cancelling or saving.
 *
 * clicked_item: save/cancel button.
 *
 * Returns a promise on the comment loading if reload_comment=true.
 */
function commentEditCancel(clicked_item, reload_comment) {
	comment_mode(clicked_item, 'view');

	var comment_container = $(clicked_item).closest('.comment-container');
	var comment_id = comment_container.data('node-id');

	if (!reload_comment) return;

	return loadComment(comment_id, {'properties.content': 1})
	.done(function(data) {
		var comment_html = data['properties']['content_html'];
		comment_container
			.find('.comment-body span')
			.removeClass('editing')
			.html(comment_html);
	})
	.fail(function(xhr) {
		if (console) console.log('Error fetching comment: ', xhr);
		toastr.error('Error canceling', xhr.responseText);
	});
}

function save_comment(is_new_comment, $commentContainer)
{
	var promise = $.Deferred();
	var commentField;
	var commentId;
	var parent_id;

	// Get data from HTML, and validate it.
	if (is_new_comment)
		commentField = $('#comment_field');
	else {
		commentField = $commentContainer.find('textarea');
		commentId = $commentContainer.data('node-id');
	}

	if (!commentField.length)
		return promise.reject("Unable to find comment field.");

	if (is_new_comment) {
		parent_id = commentField.data('parent-id');
		if (!parent_id) {
			if (console) console.log("No parent ID found in comment field data.");
			return promise.reject("No parent ID!");
		}
	}

	// Validate the comment itself.
	var comment = commentField.val();
	if (comment.length < 5) {
		if (comment.length == 0) promise.reject("Say something...");
		else promise.reject("Minimum 5 characters.");
		return promise;
	}

	// Notify callers of the fact that client-side validation has passed.
	promise.notify();

	// Actually post the comment.
	if (is_new_comment) {
		$.post('/nodes/comments/create',
			{'content': comment, 'parent_id': parent_id})
		.fail(promise.reject)
		.done(function(data) { promise.resolve(data.node_id, comment); });
	} else {
		$.post('/nodes/comments/' + commentId,
			{'content': comment})
		.fail(promise.reject)
		.done(function(resp) {
			promise.resolve(commentId, resp.data.content_html);
		});
	}

	return promise;
}

/* Used when clicking the .comment-action-submit button or by a shortcut */
function post_comment($submit_button){

	save_comment(true)
	.progress(function() {
		$submit_button
			.addClass('submitting')
			.html('<span><i class="pi-spin spin"></i> Sending...</span>');
	})
	.fail(function(xhr){
		if (typeof xhr === 'string') {
			show_comment_button_error(xhr);
		} else {
			// If it's not a string, we assume it's a jQuery XHR object.
			if (console) console.log('Error posting comment: ', xhr.responseText);
			show_comment_button_error("Try again?");
		}
		toastr.error(xhr.responseText, 'Error posting comment');
	})
	.done(function(comment_node_id) {
		$submit_button
			.removeClass('submitting')
			.html('<i class="pi-paper-plane"></i> Send');
		$('#comment_field').val('');
		$('body').trigger('pillar:comment-posted', [comment_node_id]);

		toastr.success('Comment posted!');
	});
}
