/**
 * Election Eligibility Engine (Version 2.0) — admin UI convenience.
 *
 * Purely progressive enhancement: shows/hides the eligibility filter
 * rows on the Election admin form based on the selected Scope, so staff
 * aren't shown "Department" for a National election. Nothing here
 * enforces anything — every filter combination is still fully validated
 * server-side in Election.clean() and enforced server-side by
 * apps/elections/eligibility.py, regardless of what this script does or
 * whether JavaScript is even enabled.
 */
(function ($) {
    "use strict";

    if (!$) {
        return;
    }

    $(function () {
        var $scopeField = $("#id_scope");
        if ($scopeField.length === 0) {
            return;
        }

        // Membership Category and "Approved members only" are always
        // relevant (Membership Category applies even to National
        // elections — see EXPECTED BEHAVIOUR), so they're not in this
        // map and are always left visible.
        var FIELDS_BY_SCOPE = {
            national: [],
            institution: ["eligibility_institution"],
            faculty: ["eligibility_institution", "eligibility_faculty"],
            department: ["eligibility_institution", "eligibility_faculty", "eligibility_department"],
            custom: [
                "eligibility_institution",
                "eligibility_faculty",
                "eligibility_department",
                "eligibility_level",
                "eligibility_gender",
            ],
        };

        var ALL_TOGGLABLE_FIELDS = [
            "eligibility_institution",
            "eligibility_faculty",
            "eligibility_department",
            "eligibility_level",
            "eligibility_gender",
        ];

        function fieldRow(name) {
            // Django admin renders each field's row as
            // `.form-row.field-<name>` (classic theme) — falls back to
            // no-op if a given theme structures rows differently, since
            // this is a convenience layer only.
            return $(".form-row.field-" + name);
        }

        function applyVisibility() {
            var scope = $scopeField.val();
            var visible = FIELDS_BY_SCOPE[scope] || ALL_TOGGLABLE_FIELDS;

            ALL_TOGGLABLE_FIELDS.forEach(function (name) {
                var $row = fieldRow(name);
                if ($row.length === 0) {
                    return;
                }
                if (visible.indexOf(name) !== -1) {
                    $row.show();
                } else {
                    $row.hide();
                }
            });
        }

        $scopeField.on("change", applyVisibility);
        applyVisibility();
    });
})(window.django && window.django.jQuery);
