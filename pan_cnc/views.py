from typing import Any

from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, HttpResponseRedirect
from django.views.generic import TemplateView
from django.views.generic.edit import FormView

from pan_cnc.lib import pan_utils
from pan_cnc.lib import snippet_utils


class CNCBaseAuth(LoginRequiredMixin):
    login_url = '/login'


class CNCView(CNCBaseAuth, TemplateView):
    template_name = "pan_cnc/index.html"
    # base html - allow sub apps to override this with special html base if desired
    base_html = 'pan_cnc/base.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['base_html'] = self.base_html
        return context


class CNCBaseFormView(FormView):
    """
    Base class for most CNC view functions. Will find a 'snippet' from either the POST or the session cache
    and load it into a 'service' attribute.
    GET will create a dynamic form based on the loaded snippet
    POST will save all user input into the session and redirect to next_url

    Variables defined in __init__ are instance specific variables while variables defined immedately preceeding
    this docstring are class specific variables and will be shared with child classes

    """
    # base form class, you should not need to override this
    form_class = forms.Form
    # form to render, override if you need a specific html fragment to render the form
    template_name = 'pan_cnc/dynamic_form.html'
    # Head to show on the rendered dynamic form - Main header
    header = 'Pan-OS Utils'
    # title to show on dynamic form
    title = 'Title'
    # where to go after this? once the form has been submitted, redirect to where?
    # this should match a 'view name' from the pan_cnc.yaml file
    next_url = 'provision'
    # the action of the form if it needs to differ (it shouldn't)
    action = '/'
    # the app dir should match the app name and is used to load app specific snippets
    app_dir = 'pan_cnc'
    # base html - allow sub apps to override this with special html base if desired
    base_html = 'pan_cnc/base.html'

    def __init__(self, **kwargs):
        # fields to render and fields to filter should never be shared to child classes
        # list of fields to NOT render in this instance
        self._fields_to_filter = list()
        # list of fields to ONLY render in this instance - only eval'd if fields_to_filter is blank or []
        self._fields_to_render = list()

        # currently loaded service should also never be shared
        self._service = dict()
        # name of the snippet to find and load into the service
        self._snippet = ''
        # call the super
        super().__init__(**kwargs)

    @property
    def fields_to_render(self) -> list:
        return self._fields_to_render

    @fields_to_render.setter
    def fields_to_render(self, value):
        self._fields_to_render = value

    @property
    def fields_to_filter(self):
        return self._fields_to_filter

    @fields_to_filter.setter
    def fields_to_filter(self, value):
        self._fields_to_filter = value

    @property
    def service(self):
        return self._service

    @service.setter
    def service(self, value):
        self._service = value

    @property
    def snippet(self):
        return self._snippet

    @snippet.setter
    def snippet(self, value):
        self._snippet = value

    def get_snippet(self):
        print('Getting snippet here in get_snippet')
        if 'snippet_name' in self.request.POST:
            print('found it in the POST')
            return self.request.POST['snippet_name']

        elif self.app_dir in self.request.session:
            session_cache = self.request.session[self.app_dir]
            if 'snippet_name' in session_cache:
                print('returning snippet name: %s' % session_cache['snippet_name'])
                return session_cache['snippet_name']
        else:
            print('no snippet to be found')
            return self.snippet

    def get_context_data(self, **kwargs) -> dict:
        context = super().get_context_data(**kwargs)
        form = self.generate_dynamic_form()
        context['form'] = form
        context['header'] = self.header
        context['title'] = self.title
        context['base_html'] = self.base_html

        return context

    def get(self, request, *args, **kwargs) -> Any:
        """Handle GET requests: instantiate a blank version of the form."""
        # load the snippet into the class attribute here so it's available to all other methods throughout the
        # call chain in the child classes
        snippet = self.get_snippet()
        if snippet != '':
            self.service = snippet_utils.load_snippet_with_name(snippet, self.app_dir)
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs) -> Any:
        """
        Handle POST requests: instantiate a form instance with the passed
        POST variables and then check if it's valid. If valid, save variables to the session
        and load the desired snippet
        """
        form = self.get_form()
        if form.is_valid():
            # load the snippet into the class attribute here so it's available to all other methods throughout the
            # call chain in the child classes
            self.service = snippet_utils.load_snippet_with_name(self.get_snippet(), self.app_dir)
            # go ahead and save all our current POSTed variables to the session for use later
            self.save_workflow_to_session()

            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def render_snippet_template(self) -> str:

        if 'variables' not in self.service:
            print('Service not loaded on this class!')
            return ''
        template = snippet_utils.render_snippet_template(self.service, self.app_dir, self.get_workflow())
        return template

    def save_workflow_to_session(self) -> None:
        """
        Save the current user input to the session
        :return: None
        """

        if self.app_dir in self.request.session:
            current_workflow = self.request.session[self.app_dir]
        else:
            current_workflow = dict()

        for variable in self.service['variables']:
            var_name = variable['name']
            if var_name in self.request.POST:
                print('Adding variable %s to session' % var_name)
                current_workflow[var_name] = self.request.POST.get(var_name)

        self.request.session[self.app_dir] = current_workflow

    def get_workflow(self) -> dict:
        if self.app_dir in self.request.session:
            return self.request.session[self.app_dir]
        else:
            return dict()

    def get_value_from_workflow(self, var_name, default) -> Any:
        session_cache = self.get_workflow()
        return session_cache.get(var_name, default)

    def generate_dynamic_form(self) -> forms.Form:

        dynamic_form = forms.Form()

        if self.service is None:
            print('There is not service here :-/')
            return dynamic_form

        if 'variables' not in self.service:
            print('No self.service found on this class')
            return dynamic_form

        # Get all of the variables defined in the self.service
        for variable in self.service['variables']:
            if len(self.fields_to_filter) != 0:
                if variable['name'] in self.fields_to_filter:
                    print('Skipping render of variable %s' % variable['name'])
                    continue

            elif len(self.fields_to_render) != 0:
                print(self.fields_to_render)
                if variable['name'] not in self.fields_to_render:
                    print('Skipping render of variable %s' % variable['name'])
                    continue

            field_name = variable['name']
            type_hint = variable['type_hint']
            description = variable['description']
            # if the user has entered this before, let's grab it from the session
            default = self.get_value_from_workflow(variable['name'], variable['default'])
            # Figure out which type of widget should be rendered
            # Valid widgets are dropdown, text_area, password and defaults to a char field
            if type_hint == 'dropdown' and 'dd_list' in variable:
                dd_list = variable['dd_list']
                choices_list = list()
                for item in dd_list:
                    choice = (item['value'], item['key'])
                    choices_list.append(choice)
                dynamic_form.fields[field_name] = forms.ChoiceField(choices=tuple(choices_list), label=description,
                                                                    initial=default)
            elif type_hint == "text_area":
                dynamic_form.fields[field_name] = forms.CharField(widget=forms.Textarea, label=description,
                                                                  initial=default)
            elif type_hint == "email":
                dynamic_form.fields[field_name] = forms.CharField(widget=forms.EmailInput, label=description,
                                                                  initial=default)
            elif type_hint == "number":
                dynamic_form.fields[field_name] = forms.GenericIPAddressField(label=description,
                                                                              initial=default)
            elif type_hint == "password":
                dynamic_form.fields[field_name] = forms.CharField(widget=forms.PasswordInput)
            elif type_hint == "radio" and "rad_list":
                rad_list = variable['rad_list']
                choices_list = list()
                for item in rad_list:
                    choice = (item['value'], item['key'])
                    choices_list.append(choice)
                dynamic_form.fields[field_name] = forms.ChoiceField(widget=forms.RadioSelect, choices=choices_list,
                                                                    label=description, initial=default)
            else:
                dynamic_form.fields[field_name] = forms.CharField(label=description, initial=default)

        return dynamic_form

    def form_valid(self, form):
        """
        Called once the form has been submitted
        :param form: dynamic form
        :return: rendered html response or redirect
        """
        return HttpResponseRedirect(self.next_url)


class ChooseSnippetByLabelView(CNCBaseAuth, CNCBaseFormView):
    label_name = ''
    label_value = ''

    def get_snippet(self) -> str:
        return ''

    def generate_dynamic_form(self):

        form = forms.Form()
        if self.label_name == '' or self.label_value == '':
            print('No Labels to use to filter!')
            return form

        services = snippet_utils.load_snippets_by_label(self.label_name, self.label_value, self.app_dir)

        # we need to construct a new ChoiceField with the following basic format
        # snippet_name = forms.ChoiceField(choices=(('gold', 'Gold'), ('silver', 'Silver'), ('bronze', 'Bronze')))
        choices_list = list()
        # grab each service and construct a simple tuple with name and label, append to the list
        for service in services:
            choice = (service['name'], service['label'])
            choices_list.append(choice)

        # let's sort the list by the label attribute (index 1 in the tuple)
        choices_list = sorted(choices_list, key=lambda k: k[1])
        # convert our list of tuples into a tuple itself
        choices_set = tuple(choices_list)
        # make our new field
        new_choices_field = forms.ChoiceField(choices=choices_set)
        # set it on the original form, overwriting the hardcoded GSB version

        form.fields['snippet_name'] = new_choices_field

        return form

    def post(self, request, *args, **kwargs) -> Any:
        """
        Parent class assumes a snippet has been loaded as a service already and uses that to capture all user input
        In most cases, a snippet chooser may not
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        form = self.get_form()

        if form.is_valid():
            if self.app_dir in self.request.session:
                current_workflow = self.request.session[self.app_dir]
            else:
                current_workflow = dict()

            if 'snippet_name' in self.request.POST:
                print('Adding snippet_name')
                current_workflow['snippet_name'] = self.request.POST.get('snippet_name')

            self.request.session[self.app_dir] = current_workflow

            return self.form_valid(form)
        else:
            return self.form_invalid(form)


class ChooseSnippetView(CNCBaseAuth, CNCBaseFormView):
    snippet = ''

    def get_snippet(self):
        return self.snippet

    def generate_dynamic_form(self):
        print('here we go')
        form = super().generate_dynamic_form()
        if self.service is None:
            print('Still no service around')
            return form

        if 'labels' in self.service and 'customize_field' in self.service['labels']:
            labels = self.service['labels']
            if not {'customize_label_name', 'customize_label_value'}.issubset(labels):
                print('Malformed Configure Service Picker!')

            custom_field = labels['customize_field']
            label_name = labels['customize_label_name']
            label_value = labels['customize_label_value']
            services = snippet_utils.load_snippets_by_label(label_name, label_value, self.app_dir)
        else:
            custom_field = 'snippet_name'
            services = snippet_utils.load_snippets_of_type('service', self.app_dir)

        # we need to construct a new ChoiceField with the following basic format
        # snippet_name = forms.ChoiceField(choices=(('gold', 'Gold'), ('silver', 'Silver'), ('bronze', 'Bronze')))
        choices_list = list()
        # grab each service and construct a simple tuple with name and label, append to the list
        for service in services:
            choice = (service['name'], service['label'])
            choices_list.append(choice)

        # let's sort the list by the label attribute (index 1 in the tuple)
        choices_list = sorted(choices_list, key=lambda k: k[1])
        # convert our list of tuples into a tuple itself
        choices_set = tuple(choices_list)
        # make our new field
        new_choices_field = forms.ChoiceField(choices=choices_set)
        # set it on the original form, overwriting the hardcoded GSB version

        form.fields[custom_field] = new_choices_field

        return form


class ProvisionSnippetView(CNCBaseAuth, CNCBaseFormView):
    """
    Provision Service View - This view uses the Base Auth and Form View
    The posted view is actually a dynamically generated form so the forms.Form will actually be blank
    use form_valid as it will always be true in this case.
    """
    snippet = ''
    header = 'Provision Service'
    title = 'Configure Service Sales information'

    def get_snippet(self):
        print('Getting snippet here in ProvisionSnippetView:get_snippet')
        if 'snippet_name' in self.request.POST:
            print('found snippet in post')
            return self.request.POST['snippet_name']

        elif self.app_dir in self.request.session:
            session_cache = self.request.session[self.app_dir]
            if 'snippet_name' in session_cache:
                print('returning snippet name: %s from session cache' % session_cache['snippet_name'])
                return session_cache['snippet_name']
        else:
            print('snippet is not set in ProvisionSnippetView:get_snippet')
            return self.snippet

    def form_valid(self, form):
        """
        form_valid is always called on a blank / new form, so this is essentially going to get called on every POST
        self.request.POST should contain all the variables defined in the service identified by the hidden field
        'service_id'
        :param form: blank form data from request
        :return: render of a success template after service is provisioned
        """
        service_name = self.get_value_from_workflow('snippet_name', '')

        if service_name == '':
            # FIXME - add an ERROR page and message here
            print('No Service ID found!')
            return super().form_valid(form)

        if self.service['type'] == 'template':
            template = snippet_utils.render_snippet_template(self.service, self.app_dir, self.get_workflow())
            context = dict()
            context['results'] = template
            return render(self.request, 'pan_cnc/results.html', context)

        login = pan_utils.panorama_login()
        if login is None:
            context = dict()
            context['error'] = 'Could not login to Panorama'
            return render(self.request, 'pan_cnc/error.html', context=context)

        # Always grab all the default values, then update them based on user input in the workflow
        jinja_context = dict()
        if 'variables' in self.service and type(self.service['variables']) is list:
            for snippet_var in self.service['variables']:
                jinja_context[snippet_var['name']] = snippet_var['default']

        # let's grab the current workflow values (values saved from ALL forms in this app
        jinja_context.update(self.get_workflow())
        dependencies = snippet_utils.resolve_dependencies(self.service, self.app_dir, [])
        for baseline in dependencies:
            # prego (it's in there)
            baseline_service = snippet_utils.load_snippet_with_name(baseline, self.app_dir)
            # FIX for https://github.com/nembery/vistoq2/issues/5
            if 'variables' in baseline_service and type(baseline_service['variables']) is list:
                for v in baseline_service['variables']:
                    # FIXME - Should include a way show this in UI so we have POSTED values available
                    if 'default' in v:
                        # Do not overwrite values if they've arrived from the user via the Form
                        if v['name'] not in jinja_context:
                            print('Setting default from baseline on context for %s' % v['name'])
                            jinja_context[v['name']] = v['default']

            if baseline_service is not None:
                # check the panorama config to see if it's there or not
                if not pan_utils.validate_snippet_present(baseline_service, jinja_context):
                    # no prego (it's not in there)
                    print('Pushing configuration dependency: %s' % baseline_service['name'])
                    # make it prego
                    pan_utils.push_service(baseline_service, jinja_context)

        # BUG-FIX to always just push the toplevel self.service
        pan_utils.push_service(self.service, jinja_context)
        # if not pan_utils.validate_snippet_present(service, jinja_context):
        #     print('Pushing new service: %s' % service['name'])
        #     pan_utils.push_service(service, jinja_context)
        # else:
        #     print('This service was already configured on the server')

        return super().form_valid(form)
