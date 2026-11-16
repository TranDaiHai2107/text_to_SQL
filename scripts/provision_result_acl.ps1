$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$target = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'results\restricted'))
if (-not $target.StartsWith($projectRoot + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Result directory must stay inside this workspace'
}
New-Item -ItemType Directory -Path $target -Force | Out-Null
$acl = Get-Acl -LiteralPath $target
$acl.SetAccessRuleProtection($true, $false)
foreach ($rule in @($acl.Access)) { $acl.RemoveAccessRuleSpecific($rule) }
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl.SetOwner($current)
$inherit = [System.Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
$propagate = [System.Security.AccessControl.PropagationFlags]::None
$allow = [System.Security.AccessControl.AccessControlType]::Allow
foreach ($sidText in @($current.Value, 'S-1-5-18', 'S-1-5-32-544')) {
    $sid = New-Object System.Security.Principal.SecurityIdentifier($sidText)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $sid, [System.Security.AccessControl.FileSystemRights]::FullControl,
        $inherit, $propagate, $allow)
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $target -AclObject $acl
& (Join-Path $PSScriptRoot 'verify_result_acl.ps1') -TargetPath $target
