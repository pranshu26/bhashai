import { Body, Controller, Get, Post, UseGuards } from '@nestjs/common';
import { signupSchema, loginSchema, type SignupDto, type LoginDto } from '@bhashai/shared';
import { ZodBody } from '../common/zod.pipe';
import { AuthService } from './auth.service';
import { JwtGuard } from './jwt.guard';
import { CurrentUser, type AuthUser } from './current-user.decorator';

@Controller('auth')
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @Post('signup')
  signup(@Body(new ZodBody(signupSchema)) dto: SignupDto) {
    return this.auth.signup(dto);
  }

  @Post('login')
  login(@Body(new ZodBody(loginSchema)) dto: LoginDto) {
    return this.auth.login(dto);
  }

  @Get('me')
  @UseGuards(JwtGuard)
  me(@CurrentUser() user: AuthUser) {
    return user;
  }
}
