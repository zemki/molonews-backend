/*global DateTimeShortcuts, SelectFilter*/
(function($) {
    'use strict';

    var $j = jQuery.noConflict();
    var $jet = jet.jQuery;


    var _this = this;

    var eventStart = $("div[class='form-row field-event_date']");;
    var eventEnd = $("div[class='form-row field-event_end_date']");

    // radiobuttons
    var recurringLine = $("div[class='form-row field-recurring']");
    var singleEvent = $('#id_recurring_0');
    var recurringEvent = $('#id_recurring_1');
    var recurringIrregularEvent = $('#id_recurring_2');

    // tooltips
    var tooltip_placeholder = $("#tooltip-placeholder");

    var mountTooltip = function(tooltip, id){
        var _tooltip = '<div id="'+ id +'" class="modal"><p class="tooltip-text">' + tooltip + '</p><!--a href="#" rel="modal:close">Schliessen</a--></div>';
        tooltip_placeholder.append(_tooltip);
        return $j("#"+id);
    };

    var tooltip_1_text = 'Über die Felder werden der Beginn eines Events und das Ende eines Events eingetragen. Das Event kann auch über mehrere Tage gehen.\n' +
        'Achte darauf, dass das Enddatum und die Endzeit nach dem jeweiligen Beginn liegen.'
    var tooltip_1 = mountTooltip(tooltip_1_text, "tooltip_1-text");

    var tootltip_2_text = 'Über die Felder „Event Datum“ und „Event Ende“ werden der Beginn eines Events bzw. das Ende eines Events eingetragen.\n' +
        'Außerdem können die „Wiederholungen“ des regelmäßig stattfindenden Events festgelegt werden.\n\n' +
        'Wird "Diese Vorkommen ausschließen" ausgewählt, dann werden die ausgewählten Tage in dem jeweiligen Zeitraum ausgelassen.\n' +
        'Alle anderen Tage werden bis zum „Ende des Wiederholungszeitraums“ als Termine berücksichtigt.\n\n' +
        'Über "Datum hinzufügen" können weitere Einzeldaten mit in die Terminplanung aufgenommen oder ausgeschlossen werden.\n' +
        'Das bietet sich an, wenn regelmäßige Termine durch Einzeltermine unterbrochen werden.';
    var tooltip_2 = mountTooltip(tootltip_2_text, "tooltip_2-text");

    var tooltip_3_text = 'Über die Kalenderblätter können die genauen Tage, an denen ein Event stattfindet, ausgewählt werden.\n' +
        'Darüber wird lediglich die Start- und Endzeit des ersten Events eingetragen, um bei einer Übernahme der Zeiten die jeweils gleichen Abstände zueinander zu haben';
    var tooltip_3 = mountTooltip(tooltip_3_text, "tooltip_3-text");

    var placeholder_0 = $(".id_recurring_0-tooltip");
    var placeholder_1 = $(".id_recurring_1-tooltip");
    var placeholder_2 = $(".id_recurring_2-tooltip");

    placeholder_0.on('click', function(e) {
        e.preventDefault();
        tooltip_1.modal();
    });
    placeholder_1.on('click', function(e) {
        e.preventDefault();
        tooltip_2.modal();
    });
    placeholder_2.on('click', function(e) {
        e.preventDefault();
        tooltip_3.modal();
    });
    var tooltips = [];

    // elements for recurring events
    var recurring_end_date = $('.field-recurring_event_end_date');
    var recurrences_widget = $('.field-recurrences');

    // elements for irregular events
    var calendarWidgetPlaceholder = $('#calendar-widgets');
    var childEvents = $('#event_child_parent-group');
    var calendarApplyButton = $('#calendar-button');
    var applyTimesButton = $('#applyTimes-button');

    var widget1 = $j('#calendar-widget-1');
    var widget2 = $j('#calendar-widget-2');
    var widget3 = $j('#calendar-widget-3');
    var widget4 = $j('#calendar-widget-4');

    var widgets = [widget1, widget2, widget3, widget4];

    var recurringEventElements = [
        recurring_end_date,
        recurrences_widget,
    ];

    var recurringIrregularEventElements = [
        childEvents,
        calendarWidgetPlaceholder,
        calendarApplyButton,
    ];

    var addInlineButton = null;

    var startDate = null;
    var startTime = null;
    var endDate = null;
    var endTime = null;

    var widget1StartDate = null;
    var widget1EndDate = null;
    var widget2StartDate = null;
    var widget2EndDate = null;
    var widget3StartDate = null;
    var widget3EndDate = null;
    var widget4StartDate = null;
    var widget4EndDate = null;

    function hideElements(elements){
        $.each(elements, function(index, element) {
            element.hide();
        });
    }
    function unHideElements(elements){
        $.each(elements, function(index, element) {
            element.show();
        });
    }


    function getDatesFromWidgets() {
        var dates = [];
        $.each(widgets, function(index, widget) {
            var _dates = widget.datepicker('getDates');
            _dates.forEach(function(value) {
                dates.push(value);
            });
        });
        return dates;
    }

    function compareExistingExpectedEvents(expected, existing) {
        var _missing = [];
        var missing = [];
        var invisible = [];
        var toBeRemoved = [];
        var expectedDates = [];
        var existingDates = [];

        $.each(expected, function(index, expectedDate) {
            expectedDates.push(expectedDate.getTime().toString());
        });
        $.each(Object.entries(existing), function (index, data) {
            existingDates.push(data[0]);
            if (! expectedDates.includes(data[0])){
                toBeRemoved.push(data);
            } else {
                var element = $('#'+data[1].id);
                if (element.is(':hidden')) {
                    invisible.push(element);
                }
            }
        });
        $.each(expectedDates, function(index, expectedDate){
            if(! existingDates.includes(expectedDate)) {
                _missing.push(expectedDate);
            }
        });
        _missing.sort();
        $.each(_missing, function(index, mis){
            missing.push(new Date(parseInt(mis)));
        });

        return [missing, toBeRemoved, invisible];
    }

    function addInlineDate(date) {

        $.fn.actions.addInline(date);
        //fixDateTimePickers();
    }


    function applyWidgetDates() {
        var dates = getDatesFromWidgets();
        var childs = getExistingEvents();
        var compared = compareExistingExpectedEvents(dates, childs);
        var missing = compared[0];
        var toBeRemoved = compared[1];
        var invisible = compared[2];

        $.each(missing, function(index, date){
            addInlineDate(date);
        });
        $.each(toBeRemoved, function(index, event){
            markEventForDeletion(event[1].id);
        });
        $.each(invisible, function(index, event){
            event.show();
            var checkbox = event.find('input[type="checkbox"]');
            if (checkbox.length === 1) {
                $(checkbox[0]).prop('checked', false);
            }
        });
    }

    function readMainEventValues(init) {
        if (init) {
            startDate = $('#id_event_date_0').attr('value');
            startTime = $('#id_event_date_1').attr('value');
            endDate = $('#id_event_end_date_0').attr('value');
            endTime = $('#id_event_end_date_1').attr('value');
        } else {
            startDate = dateToString($jet('#id_event_date_0').datepicker("getDate"));
            startTime = $jet('#id_event_date_1').timepicker("getTime");
            endDate = dateToString($jet('#id_event_end_date_0').datepicker("getDate"));
            endTime = $jet('#id_event_end_date_1').timepicker("getTime");
        }
    }

    function markEventForDeletion(event_id) {
        var event = $('#'+event_id);
        // find td class=delete
        // if it has checkbox -> check checkbox and hide event row
        // else click delete-link <a class=inline-deletelink>

        var _delete = event.find("td[class='delete']")[0];

        var checkbox = $(_delete).find('input[type="checkbox"]');
        if (checkbox.length === 1){
            $(checkbox[0]).attr('checked', 'true');
            event.hide();
        }
        var deleteLink = event.find("a[class='inline-deletelink']");
        if (deleteLink.length === 1){
            deleteLink[0].click();
        }

    }


    function getExistingEvents() {
        var childEventsObject = {};
        childEvents.find('.form-row').each(function(index, _datetime) {
            if (! _datetime.classList.contains("empty-form")) {
                var datetime = $("#" + _datetime.id);
                var start = datetime.find(".field-event_date");
                var _startDate = start.find('.vDateField').attr('value');
                var _startTime = start.find('.vTimeField').attr('value');

                var end = datetime.find(".field-event_end_date");
                var _endDate = end.find('.vDateField').attr('value');
                var _endTime = end.find('.vTimeField').attr('value');

                var _start = stringToDate(_startDate);
                childEventsObject[_start.getTime()] = {
                    startDate: _startDate, startTime: _startTime, endDate: _endDate, endTime: _endTime, id: _datetime.id
                };
            }
        });

        return childEventsObject;
    }

    function djangoDateTimeFormatToJs(format) {
        return format.toLowerCase().replace(/%\w/g, function(format) {
            format = format.replace(/%/,"");
            return format + format;
        });
    }

    var fixDateTimePickers = function(row) {
        //row.find('.datetime').each(function () {
        //    var $dateTime = $j(this);
        //    var $dateField = $dateTime.find('.vDateField');
        //});
        row.find('.vDateField').each(function () {
            var $dateField = $j(this);
            $dateField.removeClass('hasDatepicker');
            var jetDateField = $jet('#'+$dateField.attr('id'));
            jetDateField.datepicker({
                showButtonPanel: true,
                nextText: '',
                prevText: '',
                //dateFormat: djangoDateTimeFormatToJs(DATE_FORMAT),
            });
            var $dateLink = jetDateField.next('.vDateField-link');
            $dateLink.on('click', function (e) {
                if (jetDateField.datepicker('widget').is(':visible')) {
                    jetDateField.datepicker('hide');
                } else {
                    jetDateField.datepicker('show');
                }
                e.preventDefault();
            });
        });

        row.find('.vTimeField').each(function () {
            var $timeField = $j(this);
            $timeField.removeClass('hasTimepicker');
            var jetTimeField =  $jet('#'+$timeField.attr('id'));
            jetTimeField.timepicker({
                showPeriodLabels: false,
                showCloseButton: true,
                showNowButton: true,
                //timeFormat: "H:i:s",
            });
            var $timeLink = jetTimeField.next('.vTimeField-link');
            $timeLink.on('click', function (e) {
                if (jetTimeField.datepicker('widget').is(':visible')) {
                    jetTimeField.datepicker('hide');
                } else {
                    jetTimeField.timepicker('show');
                }
                e.preventDefault();
            });
        });
    };


    function inlineRowAdded(event, $row, formsetName) {

        // TODO maybe not needed anymore
        fixDateTimePickers($row);

    }

    function inlineRowRemoved(event, $row, formsetName) {

        // TODO remove from calendar widget
    }


    function initCalendarWidget(widget, widgetStartDate, widgetEndDate) {
        widget.datepicker({
            language: "de",
            multidate: true,
            startDate: widgetStartDate,
            endDate: widgetEndDate,
            todayHighlight: true,
            minViewMode: 0,
            maxViewMode: 0,
            //updateViewDate: false,
        });
    }

    function setCalendarWidgetDates(widget, dates) {
        if (dates.length > 0) {
            widget.datepicker('setDates', dates);
        }
    }

    function dateToString(date){
        if (date === null) {
            return null;
        }
        return date.getDate() + "." + (date.getMonth() + 1) + "." + date.getFullYear();
    }

    function stringToDate(dateString) {
        var dateParts = dateString.split('.');
        return new Date(dateParts[2], dateParts[1] - 1, dateParts[0]);
    }

    function stringToDateTime(dateString, timeString) {
        if (dateString === null) {
            return null;
        }
        var dateParts = dateString.split('.');
        var timeParts = timeString.split(':');
        return new Date(dateParts[2], dateParts[1] - 1, dateParts[0], timeParts[0], timeParts[1]);
    }

    function mapExistingEventsToWidget() {
        var existingEvents = getExistingEvents();

        var widget1Dates = [];
        var widget2Dates = [];
        var widget3Dates = [];
        var widget4Dates = [];

        $.each(Object.entries(existingEvents), function (index, data) {
            var date = data[0];

            if ((+widget1StartDate <= date) && (date <= +widget1EndDate)) {
                widget1Dates.push(data[1].startDate);
            }
            if ((+widget2StartDate <= date) && (date <= +widget2EndDate)) {
                widget2Dates.push(data[1].startDate);
            }
            if ((+widget3StartDate <= date) && (date <= +widget3EndDate)) {
                widget3Dates.push(data[1].startDate);
            }
            if ((+widget4StartDate <= date) && (date <= +widget4EndDate)) {
                widget4Dates.push(data[1].startDate);
            }
        });

        setCalendarWidgetDates(widget1, widget1Dates);
        setCalendarWidgetDates(widget2, widget2Dates);
        setCalendarWidgetDates(widget3, widget3Dates);
        setCalendarWidgetDates(widget4, widget4Dates);

    }


    function mountCalendars() {

        readMainEventValues(true);

        var parts = startDate.split('.');
        var today = new Date(parts[2], parts[1] - 1, parts[0]);
        widget1StartDate = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
        widget1EndDate = new Date(today.getFullYear(), today.getMonth() + 1, 0);

        widget2StartDate = new Date(today.getFullYear(), today.getMonth() + 1, 1);
        widget2EndDate = new Date(today.getFullYear(), today.getMonth() + 2, 0);
        widget3StartDate = new Date(today.getFullYear(), today.getMonth() + 2, 1);
        widget3EndDate = new Date(today.getFullYear(), today.getMonth() + 3, 0);
        widget4StartDate = new Date(today.getFullYear(), today.getMonth() + 3, 1);
        widget4EndDate = new Date(today.getFullYear(), today.getMonth() + 4, 0);

        initCalendarWidget(widget1, widget1StartDate, widget1EndDate);
        initCalendarWidget(widget2, widget2StartDate, widget2EndDate);
        initCalendarWidget(widget3, widget3StartDate, widget3EndDate);
        initCalendarWidget(widget4, widget4StartDate, widget4EndDate);

        var button = $('<button/>', {
            text: 'Übernehmen',
            type: 'button',
            click: applyWidgetDates,
        });
        calendarApplyButton.append(button);

        mapExistingEventsToWidget();


        applyTimesButton = $('<button/>', {

            text: 'Zeiten übernehmen',
            type: 'button',
            click: applyMainEventTimes,
        });
        calendarApplyButton.append(applyTimesButton);

    }

    function applyMainEventTimes() {
        readMainEventValues();

        var events = getExistingEvents();
        var _endDelta = null;
        if (endDate != null && endTime != null) {
            var _startDate = stringToDateTime(startDate, startTime);
            var _endDate = stringToDateTime(endDate, endTime);
            _endDelta = _endDate.getTime() - _startDate.getTime();
        }

        $.each(events, function(index, event){
            $('#' + event.id).find('.field-event_date').find('.vTimeField').attr('value', startTime);
            if (_endDelta !== null){
                var eventStart = stringToDateTime(event.startDate, startTime);
                var eventEnd = new Date(eventStart.getTime() + _endDelta);
                var _endDate = dateToString(eventEnd);
                var _endTime = eventEnd.getHourMinuteSecond();
                $('#' + event.id).find('.field-event_end_date').find('.vDateField').attr('value', _endDate);
                $('#' + event.id).find('.field-event_end_date').find('.vTimeField').attr('value', _endTime);
            }
        });
    }

    //function appendMainEventToInlines() {
    //    eventStart.insertAfter();
    //    eventEnd.insertAfter(eventStart);
    //}
    //function appendMainEventToRecurring(){
    //    eventStart.insertAfter(recurringLine);
    //    eventEnd.insertAfter(eventStart);
    //}


    function set_recurring_0(){
        hideElements(recurringEventElements);
        hideElements(recurringIrregularEventElements);
    }
    function set_recurring_1(){
        unHideElements(recurringEventElements);
        hideElements(recurringIrregularEventElements);
    }
    function set_recurring_2(){
        hideElements(recurringEventElements);
        unHideElements(recurringIrregularEventElements);

    }

    function apply_selection(selectedMode) {
        switch(selectedMode) {
            case 0:
                // not recurring
                set_recurring_0();
                break;
            case 1:
                // recurring regularly
                set_recurring_1();
                break;
            case 2:
                // recurring irregularly
                set_recurring_2();
                break;
            default:
                // should not happen
        }
    }




    $(document).ready(function() {
        if (singleEvent.is(':checked')) {
            apply_selection(0);
        }
        if (recurringEvent.is(':checked')) {
            apply_selection(1);
        }
        if (recurringIrregularEvent.is(':checked')) {
            apply_selection(2);
        }
        if ((! singleEvent.is(':checked')) && (! recurringEvent.is(':checked')) && (! recurringIrregularEvent.is(':checked'))){
            singleEvent.click();
        }
        mountCalendars();

        $(document).on('formset:added', function(event, $row, formsetName) {
            // Row added
            inlineRowAdded(event, $row, formsetName);
        });

        $(document).on('formset:removed', function(event, $row, formsetName) {
            // Row removed
            inlineRowRemoved(event, $row, formsetName);
        });

     });
    singleEvent.click(function() {apply_selection(0);});
    recurringEvent.click(function() {apply_selection(1);});
    recurringIrregularEvent.click(function() {apply_selection(2);});
})(django.jQuery);
