# fix_template_names.py
import os


def check_template_references():
    # List of actual template files
    actual_templates = set(os.listdir('templates'))
    print("Actual template files:", sorted(actual_templates))

    # Check app.py for template references
    with open('app.py', 'r', encoding='utf-8') as file:
        content = file.read()

    # Find all render_template calls
    import re
    template_refs = re.findall(r"render_template\('([^']+)'\)", content)

    print("\nTemplate references in app.py:")
    for ref in set(template_refs):
        status = "✓ EXISTS" if f"{ref}" in actual_templates else "✗ MISSING"
        print(f"  {status}: {ref}")

    # Check for register.html vs register_member.html
    if 'register.html' in template_refs and 'register_member.html' in actual_templates:
        print("\n⚠️  Found mismatch: app.py uses 'register.html' but file is 'register_member.html'")
        fix = input("Fix by renaming file to register.html? (y/n): ")
        if fix.lower() == 'y':
            os.rename('templates/register_member.html',
                      'templates/register.html')
            print("✓ File renamed successfully!")

    return template_refs


if __name__ == '__main__':
    check_template_references()
