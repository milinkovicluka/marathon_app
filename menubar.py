import rumps

from core.countdown import format_countdown, time_until_race


class MarathonCountdownApp(rumps.App):
    def __init__(self) -> None:
        super().__init__(
            "Marathon Countdown",
            title=format_countdown(time_until_race()),
        )

    @rumps.timer(60)
    def refresh_countdown(self, _: rumps.Timer) -> None:
        self.title = format_countdown(time_until_race())


if __name__ == "__main__":
    MarathonCountdownApp().run()
