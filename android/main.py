import flet as ft
import requests
import json


def main(page: ft.Page):
    page.title = "DHCP/DNS Host Manager"
    page.padding = 20
    page.window_width = 800  # Fixed width for desktop
    page.window_height = 600
    page.window_resizable = False

    # Color schemes
    DARK_BG = "#343f48"
    LIGHT_BG = "#f5f5f5"
    DARK_TEXT = "#ffd700"
    LIGHT_TEXT = "#343f48"

    api_url = ""

    # Create buttons first
    add_button = ft.ElevatedButton("Add Host", on_click=lambda _: add_host_clicked())
    change_ip_button = ft.ElevatedButton("Change API IP", on_click=lambda _: show_ip_dialog())

    # Load saved theme preference
    def load_theme_preference():
        try:
            with open('theme_preference.json', 'r') as f:
                return json.load(f)['dark_mode']
        except:
            return True  # Default to dark mode if file doesn't exist

    def save_theme_preference(dark_mode):
        with open('theme_preference.json', 'w') as f:
            json.dump({'dark_mode': dark_mode}, f)

    def set_theme(dark_mode):
        page.theme_mode = "dark" if dark_mode else "light"
        page.bgcolor = DARK_BG if dark_mode else LIGHT_BG
        update_button_colors(dark_mode)
        update_ip_dialog_colors(dark_mode)
        save_theme_preference(dark_mode)
        page.update()

    def update_button_colors(dark_mode):
        text_color = DARK_TEXT if dark_mode else LIGHT_TEXT
        bg_color = DARK_BG if dark_mode else LIGHT_BG
        add_button.style = ft.ButtonStyle(color=text_color, bgcolor=bg_color)
        change_ip_button.style = ft.ButtonStyle(color=text_color, bgcolor=bg_color)

    def update_ip_dialog_colors(dark_mode):
        ip_dialog.bgcolor = DARK_BG if dark_mode else LIGHT_BG
        ip_dialog.title.color = DARK_TEXT if dark_mode else LIGHT_TEXT
        for action in ip_dialog.actions:
            action.style = ft.ButtonStyle(color=DARK_TEXT if dark_mode else LIGHT_TEXT,
                                          bgcolor=DARK_BG if dark_mode else LIGHT_BG)

    # Set initial theme
    initial_dark_mode = load_theme_preference()

    def set_api_url(e):
        nonlocal api_url
        ip_address = ip_input.value
        api_url = f"http://{ip_address}:8080/api"
        ip_dialog.open = False
        page.update()
        update_host_list()

    def show_ip_dialog():
        update_ip_dialog_colors(page.theme_mode == "dark")
        ip_dialog.open = True
        page.update()

    ip_input = ft.TextField(label="Enter Raspberry Pi IP Address", bgcolor="white", color="black")
    ip_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Enter Raspberry Pi IP Address"),
        content=ft.Container(content=ip_input, padding=10),
        actions=[ft.ElevatedButton(text="Connect", on_click=set_api_url)],
        actions_alignment="end",
    )

    page.dialog = ip_dialog

    def get_hosts():
        response = requests.get(f"{api_url}/hosts")
        return response.json()

    def add_host(mac, hostname, ip=None):
        data = {"mac": mac, "hostname": hostname}
        if ip:
            data["ip"] = ip
        response = requests.post(f"{api_url}/hosts", json=data)
        return response.json()

    def delete_host(mac):
        response = requests.delete(f"{api_url}/hosts/{mac}")
        return response.json()

    def update_host_list():
        try:
            hosts = get_hosts()
            hosts_view.controls.clear()
            for host in hosts:
                hosts_view.controls.append(
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column([
                                ft.Text(host['hostname'], size=18, weight="bold",
                                        color=DARK_TEXT if page.theme_mode == "dark" else LIGHT_TEXT),
                                ft.Text(f"MAC: {host['mac']}", color="white" if page.theme_mode == "dark" else "black"),
                                ft.Text(f"IP: {host['ip']}", color="white" if page.theme_mode == "dark" else "black"),
                                ft.Row([
                                    ft.ElevatedButton("Edit", on_click=lambda _, h=host: edit_host(h),
                                                      style=ft.ButtonStyle(
                                                          color=DARK_TEXT if page.theme_mode == "dark" else LIGHT_TEXT,
                                                          bgcolor=DARK_BG if page.theme_mode == "dark" else LIGHT_BG)),
                                    ft.ElevatedButton("Delete", on_click=lambda _, h=host: confirm_delete(h),
                                                      style=ft.ButtonStyle(
                                                          color=DARK_TEXT if page.theme_mode == "dark" else LIGHT_TEXT,
                                                          bgcolor=DARK_BG if page.theme_mode == "dark" else LIGHT_BG))
                                ], alignment=ft.MainAxisAlignment.END)
                            ]),
                            padding=10
                        ),
                        elevation=4,
                        margin=10
                    )
                )
            page.update()
        except requests.RequestException:
            # Create a SnackBar to notify the user about the connection issue
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Failed to connect to the API. Please check the IP address.", color="white"),

            )

            # Set the background color of the SnackBar to red
            page.snack_bar.bgcolor = "red"
            page.snack_bar.open = True  # Open the SnackBar immediately

            # Update the page to reflect changes
            page.update()

    def add_host_clicked():
        try:
            add_host(mac_field.value, hostname_field.value, ip_field.value)
            mac_field.value = ""
            hostname_field.value = ""
            ip_field.value = ""
            page.update()
            update_host_list()
        except requests.RequestException:
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Failed to add host. Please check your connection.", color="white"),
                action=ft.SnackBarAction("Change IP", on_click=lambda _: show_ip_dialog())
            )
            page.snack_bar.bgcolor = "red"
            page.snack_bar.open = True
            page.update()

    def confirm_delete(host):
        def delete_confirmed(e):
            try:
                delete_host(host['mac'])
                update_host_list()
                page.dialog.open = False
                page.update()
            except requests.RequestException:
                page.snack_bar = ft.SnackBar(
                    content=ft.Text("Failed to delete host. Please check your connection.", color="white"),
                    action=ft.SnackBarAction("Change IP", on_click=lambda _: show_ip_dialog())
                )
                page.snack_bar.bgcolor = "red"
                page.snack_bar.open = True
                page.update()

        def cancel_delete(e):
            page.dialog.open = False
            page.update()

        page.dialog = ft.AlertDialog(
            title=ft.Text(f"Delete {host['hostname']}?", color=DARK_TEXT if page.theme_mode == "dark" else LIGHT_TEXT),
            content=ft.Text("This action cannot be undone.", color="white" if page.theme_mode == "dark" else "black"),
            actions=[
                ft.TextButton("Cancel", on_click=cancel_delete,
                              style=ft.ButtonStyle(color=DARK_TEXT if page.theme_mode == "dark" else LIGHT_TEXT)),
                ft.TextButton("Delete", on_click=delete_confirmed, style=ft.ButtonStyle(color="red"))
            ],
            bgcolor=DARK_BG if page.theme_mode == "dark" else LIGHT_BG,
        )
        page.dialog.open = True
        page.update()

    def edit_host(host):
        def save_edit(e):
            # Implement edit functionality here
            # You'll need to add an API endpoint for editing hosts
            page.dialog.open = False
            update_host_list()
            page.update()

        def cancel_edit(e):
            page.dialog.open = False
            page.update()

        edit_mac = ft.TextField(label="MAC Address", value=host['mac'], bgcolor="white", color="black")
        edit_hostname = ft.TextField(label="Hostname", value=host['hostname'], bgcolor="white", color="black")
        edit_ip = ft.TextField(label="IP Address", value=host['ip'], bgcolor="white", color="black")

        page.dialog = ft.AlertDialog(
            title=ft.Text(f"Edit {host['hostname']}", color=DARK_TEXT if page.theme_mode == "dark" else LIGHT_TEXT),
            content=ft.Column([edit_mac, edit_hostname, edit_ip]),
            actions=[
                ft.TextButton("Cancel", on_click=cancel_edit,
                              style=ft.ButtonStyle(color=DARK_TEXT if page.theme_mode == "dark" else LIGHT_TEXT)),
                ft.TextButton("Save", on_click=save_edit,
                              style=ft.ButtonStyle(color=DARK_TEXT if page.theme_mode == "dark" else LIGHT_TEXT))
            ],
            bgcolor=DARK_BG if page.theme_mode == "dark" else LIGHT_BG,
        )
        page.dialog.open = True
        page.update()

    mac_field = ft.TextField(label="MAC Address", bgcolor="white", color="black")
    hostname_field = ft.TextField(label="Hostname", bgcolor="white", color="black")
    ip_field = ft.TextField(label="IP Address (optional)", bgcolor="white", color="black")

    hosts_view = ft.ListView(expand=1, spacing=10, padding=20)

    def toggle_theme(e):
        new_mode = not (page.theme_mode == "dark")
        set_theme(new_mode)
        theme_toggle.value = new_mode
        update_host_list()  # Refresh the host list to update colors

    theme_toggle = ft.Switch(label="Dark mode", value=initial_dark_mode, on_change=toggle_theme)

    page.add(
        ft.Row([
            ft.Text("DHCP/DNS Host Manager", size=24, weight="bold", color=DARK_TEXT),
            change_ip_button,
            theme_toggle
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("Add New Host", size=18, weight="bold",
                            color=DARK_TEXT if page.theme_mode == "dark" else DARK_TEXT),
                    ft.Row([mac_field, hostname_field, ip_field], wrap=True),
                    add_button
                ]),
                padding=10
            ),
            elevation=4,
            margin=10
        ),
        hosts_view,
    )

    set_theme(initial_dark_mode)
    show_ip_dialog()


ft.app(target=main)
