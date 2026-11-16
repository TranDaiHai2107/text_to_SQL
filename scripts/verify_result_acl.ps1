param([Parameter(Mandatory = $true)][string]$TargetPath, [switch]$AllowSafeInherited)
$ErrorActionPreference = 'Stop'
$item = [System.IO.DirectoryInfo]::new($TargetPath)
if (-not $item.Exists) { throw 'Result directory does not exist' }
$acl = $item.GetAccessControl()
$currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowed = @($currentSid, 'S-1-5-18', 'S-1-5-32-544')
$unexpected = @()
$userFullControl = $false
foreach ($rule in $acl.Access) {
    try {
        $sid = $rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
    } catch {
        $unexpected += [string]$rule.IdentityReference
        continue
    }
    if ($sid -notin $allowed -or $rule.AccessControlType -ne 'Allow') {
        $unexpected += $sid
    }
    if ($sid -eq $currentSid -and $rule.AccessControlType -eq 'Allow' -and
        (($rule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::FullControl) -eq
         [System.Security.AccessControl.FileSystemRights]::FullControl)) {
        $userFullControl = $true
    }
}
$safe = ($acl.AreAccessRulesProtected -or $AllowSafeInherited) -and $userFullControl -and ($unexpected.Count -eq 0)
$safeText = if ($safe) { 'true' } else { 'false' }
$protectedText = if ($acl.AreAccessRulesProtected) { 'true' } else { 'false' }
$userText = if ($userFullControl) { 'true' } else { 'false' }
[Console]::Out.WriteLine('{"safe":' + $safeText + ',"inherited_rules_disabled":' +
    $protectedText + ',"current_user_full_control":' + $userText +
    ',"unexpected_rule_count":' + $unexpected.Count + '}')
