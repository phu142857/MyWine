from dataclasses import dataclass

@dataclass
class EmbeddedWindow:
    win_id: int
    native_width: int = 0
    native_height: int = 0

    @property
    def aspect_ratio(self) -> float:
        if self.native_height == 0:
            return 1.0

        return self.native_width / self.native_height

        
