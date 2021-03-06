from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils.safestring import mark_safe
from django.urls import reverse, reverse_lazy
from django.views import generic
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect


from . import models
from . import forms
import json

# Create your views here.

@login_required(login_url="login")
def home(request):
	user = request.user
	all_projects = models.Project.objects.get_all_projects()
	categories = models.Project.objects.get_all_categories()


	# Get relevant projects of user
	# All members and subscribed projects
	projects = models.Project.objects.get_project_of_user(user.username)
	# Only subscribed
	subscriptions = models.Project.objects.get_project_subscribed_by(user.username)

	return render(request, 'thehub/home.html', {"user": request.user,
												"all_projects": all_projects,
												"projects":projects, 
												"subscriptions": subscriptions, 
												"categories": categories})

@login_required(login_url="login")
def project(request, project_name):
	"""
	View to render the profile of the given project
	"""
	user = request.user
	# Get all projects and subscribed projects of current user
	projects = models.Project.objects.get_project_of_user(user.username)
	subscriptions = models.Project.objects.get_project_subscribed_by(user.username)
	# Only owned projects
	owned_projects = models.Project.objects.get_project_owned_by(user.username)

	# Get the current project that will be displayed
	project = models.Project.objects.get_project_by_name(project_name)

	# Get the list of project that the current user is asking for membership (pending request)
	pending_membership = models.MemberRequest.objects.filter(user__exact=user)
	pending_projects = []

	for pending in pending_membership:
		pending_projects.append(pending.project)

	# Order all the post by newest first
	posts = models.Post.objects.get_parent_posts_of_project(project_name)

	children_posts = {}
	if posts:
		posts = posts.order_by("-id")
        # Get all children of relevant post
		for post in posts:
			# Let's children post be ordered by oldest first to make a flow for the conversation
			children_posts[post.id] = models.Post.objects.get_chilren_of_post(post.id)

	# The only people who can post update is member, not subscriber
	canUpdate = False
	for a_project in projects:
		if a_project.project_name == project.project_name:
			canUpdate = True
			break
	

	return render(request, 'thehub/project-profile.html', {"projects":projects,
                    										"subscriptions": subscriptions,
                                                        	"owned_projects": owned_projects,
															"project":project,
															"posts": posts,
															"canUpdate": canUpdate,
															"children_posts": children_posts,
															"pending_projects": pending_projects})

def __createPost(form, user, project, parent_post_id=None):
	"""
	Method to create a post from a valid MemberPost form
	"""
	post = form.save(commit=False)
	post.user = user
	if parent_post_id is not None:
		post.parent = models.Post.objects.get(id=parent_post_id)
	post.project = project
	post.save()

	return post
	

@login_required(login_url="login")
@require_POST
def makePost(request, project_name=None, parent_post_id=None):
	"""
	The view to handle creating a post. If parent is said, that means this is a response.
	This view only accepts the POST request.

	This view will reload the current project page if the post is created successfully.
	"""
	if project_name is None:
		return HttpResponse("Not found")
	user = request.user
	current_project = models.Project.objects.get_project_by_name(project_name=project_name)
	form = forms.MemberPostForm(request.POST)
	if form.is_valid():
		__createPost(form, user, current_project, parent_post_id)
		return redirect("project", project_name=current_project.project_name)
	else:
		# If the form content is empty, this error message will be displayed
		return HttpResponse("The post content cannot be empty")

@login_required(login_url="login")
def makeRespond(request, project_name=None, parent_post_id=None):
	"""
	The view to handle ajax call when a user respond to a comment

	Return JSON object for front end to render to newly-updated comment
	"""
	if project_name is None:
		return HttpResponse("Not found")
	user = request.user
	current_project = models.Project.objects.get_project_by_name(project_name=project_name)

	form = forms.MemberPostForm(request.POST)
	if form.is_valid():
		post = __createPost(form, user, current_project, parent_post_id)
		return_post = [as_json_post(post)]

		return JsonResponse(json.dumps(return_post), safe=False)
	else:
		return HttpResponse("Respond must have content")



@login_required(login_url="login")
def manageSubscription(request, project_name):
	"""
	Method to manage the subscription status of the logged in user with given project.
	The view will subscribe/unsubscribe the user from the project when it is called, depends on the current status
	"""
	user = request.user
	project = models.Project.objects.get_project_by_name(project_name)
	if (user in project.subscribers.all()):
		# This is a current subscriber, remove this user from the list
		project.subscribers.remove(user)
	else:
		# This is a new subscriber, add this user to the list
		project.subscribers.add(user)
	# Reload the project page after finish the subscription
	return redirect("project", project_name=project_name)
	

@login_required(login_url="login")
def manageMemberRequest(request, project_name):
	"""
	Method to manage the member request of the given project
	If a member of this project send in a request, he will leave the project.
	If other user send in this request, he will created a MemberRequest to the owner and wait for approval.
	The "Ask to join" button will be disabled if the request is pending
	"""
	user = request.user
	project = models.Project.objects.get_project_by_name(project_name)

	if user in project.members.all():
		# If this is a current member, this is a "leave" request
		project.members.remove(user)
	else:
		# This is a request to be member
		# Create the request in database
		request = models.MemberRequest.objects.create_request(project, user)
	
	return redirect("project", project_name=project_name)

@login_required(login_url="login")
def approveDeclineMemberRequest(request, member_request_id, result):
	"""
	Method to approve or decline a request to join a project.

	Only the owner should have this access.
	"""

	user = request.user
	owned_project = models.Project.objects.get_project_owned_by(user.username)
	member_request = models.MemberRequest.objects.get(id=member_request_id)

	if member_request.project in owned_project and (result=="True" or result=="False"):
		if result == "True":
			member_request.project.members.add(member_request.user)
		models.MemberRequest.objects.filter(id=member_request_id).delete()
		return redirect("profile")
	# If this URL is accessed by accident, display the error
	else:
		return HttpResponse("You do not have access to this URL or the syntax is invalid")
	

def as_json_post(post):
	"""
	Convert the current post model into a dictionary so it can be passed as json data 
	"""
	parent = post.parent.id if post.parent is not None else ""
	return dict(id=post.id,
             content=post.content,
             time_posted=str(post.time_posted),
             parent= parent,
			 type = post.get_type_display(),
             user=post.user.username, project=post.project.project_name)


@login_required(login_url="login")
def getUserUpdate(request, username, post_id=None):
	"""
	This view is a used to deal with ajax request for user profile update
	"""
	# Sort post in ascending order of id, so the older view will be update to front end first when doing looping
	if post_id is None:
		return JsonResponse({})
	query_posts = [post for post in models.Post.objects.get_post_user_intested(username)
											.filter(id__gt=post_id)
											.order_by("id")]
	
	update_posts = [as_json_post(post) for post in query_posts]
	return JsonResponse(json.dumps(update_posts), safe=False)

@login_required(login_url="login")
def getProjectUpdate(request, project_name, post_id=None):
	"""
	This view is used to handle ajax request for getting new posts updated from ajax.
	"""
	# This handles the base case where no post_id is specified to look up
	if post_id is None:
		return JsonResponse({})
	else:
		posts = [as_json_post(post) for post in models.Post.objects
												.get_all_posts_of_project(project_name)
												.filter(id__gt=post_id)
												.order_by("-id")]
		return JsonResponse(json.dumps(posts), safe=False)
	
def as_json_project(project):
	"""
	Method to convert a project to a dictionary for json response
	"""
	return dict(project_name = project.project_name,
				owner = str(project.owner),
				description = project.description,
				url = reverse("project", args=[project.project_name]))

@login_required(login_url="login")
def filterProjectByCategory(request, category):
	"""
	Method to filter all projects in database using category
	"""
	if (category == 'All'):
		filtered_projects = models.Project.objects.get_all_projects()	
	else:
		filtered_projects = models.Project.objects.get_projects_by_category(category)
	projects = [as_json_project(project) for project in filtered_projects]
	return JsonResponse(json.dumps(projects), safe=False)

@login_required(login_url="login")
def searchProjectsByKeywords(request, keywords=None):
	"""
	Method to search for project where some keywords appears
	"""
	projects = None

	keywordsList = keywords.split()
	# Find all projects that contains at least one word within the set of keywords
	for keyword in keywordsList:
		if projects is not None:
			projects = projects | models.Project.objects.filter(
				project_name__icontains=keyword) | models.Project.objects.filter(description__icontains=keyword)
		else:
			projects = models.Project.objects.filter(
				project_name__icontains=keyword) | models.Project.objects.filter(description__icontains=keyword)
	
	if projects is not None:
		# Remove duplication
		projects = projects.distinct()
		returnedProject = [as_json_project(project) for project in projects]
		return JsonResponse(json.dumps(returnedProject), safe=False)
	else:
		return JsonResponse(json.dumps([]), safe=False)

class CreateProject(generic.CreateView):
	"""
	Class based view to create a new project. Using this generic view will helps us do the form validation easier
	"""

	form_class = forms.ProjectForm
	template_name = "thehub/project_form.html"

	def form_valid(self, form):
		self.object = form.save(commit=False)
		self.object.owner = self.request.user
		self.object.save()
		return HttpResponseRedirect(self.get_success_url())

	def get_success_url(self):
		return reverse_lazy("project", args=[self.object.project_name])

@login_required(login_url="login")
def deleteProject(request, project_name):
	"""
	Method to delete a project from the hub, this view can only be used by the owner
	"""

	user = request.user
	owned_projects = models.Project.objects.get_project_owned_by(user.username)
	project_to_delete = models.Project.objects.get_project_by_name(project_name)

	if project_to_delete in owned_projects:
		models.Project.objects.filter(project_name=project_name).delete()
		return redirect("profile")
	else:
		return HttpResponse("You are not the owner of this project")




	
