jsPsych.plugins["scene-choice"] = (function() {

  var plugin = {};

  jsPsych.pluginAPI.registerPreload('scene-choice', 'stimulus', 'image');

  plugin.info = {
    name: 'scene-choice',
    description: '',
    parameters: {

    }
  }

  plugin.trial = function(display_element, trial) {

    var data = trial.data;

    // display stimulus
    var html = '<img src="/renders/'+data.labeled_frame_path+'" id="scene-stimulus"></img>';

    html += '<div class="scene-prompt">' + data.prompt + '</div>';

    //display buttons
    html += '<div id="scene-choice-btngroup">';
    var referents = Object.keys(data.referents);
    for (var i = 0; i < referents.length; i++) {
      html += '<div class="scene-choice-button" style="display: inline-block; margin: 0px 8px" id="scene-choice-button-' + i +'" data-choice="'+referents[i]+'"><button class="jspsych-btn">'+referents[i]+'</button></div>';
    }
    html += '</div>';

    display_element.innerHTML = html;

    // start timing
    var start_time = Date.now();

    for (var i = 0; i < referents.length; i++) {
      display_element.querySelector('#scene-choice-button-' + i).addEventListener('click', function(e){
        var choice = e.currentTarget.getAttribute('data-choice'); // don't use dataset for jsdom compatibility
        after_response(choice);
      });
    }

    // store response
    var response = {
      prompt_type: data.prompt_type,
      prompt: data.prompt,

      scene: data.scene,
      frame: data.frame,
      relation: data.relation,
      referents: data.referents,

      rt: null,
      choice: null
    };

    // function to handle responses by the subject
    function after_response(choice) {

      // measure rt
      console.log(response);
      var end_time = Date.now();
      var rt = end_time - start_time;
      response.choice = choice;
      response.rt = rt;

      // after a valid response, the stimulus will have the CSS class 'responded'
      // which can be used to provide visual feedback that a response was recorded
      display_element.querySelector('#scene-stimulus').className += ' responded';

      // disable all the buttons after a response
      var btns = document.querySelectorAll('.scene-choice-button button');
      for(var i=0; i<btns.length; i++){
        //btns[i].removeEventListener('click');
        btns[i].setAttribute('disabled', 'disabled');
      }

      // kill any remaining setTimeout handlers
      jsPsych.pluginAPI.clearAllTimeouts();

      // clear the display
      display_element.innerHTML = '';

      // move on to the next trial
      jsPsych.finishTrial(response);
    };


    // // hide image if timing is set
    // if (trial.stimulus_duration !== null) {
    //   jsPsych.pluginAPI.setTimeout(function() {
    //     display_element.querySelector('#scene-stimulus').style.visibility = 'hidden';
    //   }, trial.stimulus_duration);
    // }

    // // end trial if time limit is set
    // if (trial.trial_duration !== null) {
    //   jsPsych.pluginAPI.setTimeout(function() {
    //     end_trial();
    //   }, trial.trial_duration);
    // }

  };

  return plugin;
})();
